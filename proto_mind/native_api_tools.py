"""Explicit API function-call turns. Each completed call is executed at most once."""
from __future__ import annotations

import http.client
import json
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

from proto_mind.native_workspace_tools import TOOLS, GUIDANCE, validate_arguments
from proto_mind.native_progress import WorkLog


def run_api_tools(transport, model, instructions, history, prompt, on_delta):
    connection = transport.connection
    responses = connection['format'] == 'responses'
    conversation = [*history, {'role': 'user', 'content': prompt}]
    seen = set()
    progress = WorkLog(transport.on_progress, "chat")
    outcome = "failed"
    definitions = [{'type': 'function', 'name': row['name'], 'description': row['description'],
                    'parameters': row['inputSchema'], 'strict': True} for row in TOOLS]
    try:
        while not transport.cancelled.is_set():
            if len(json.dumps(conversation, ensure_ascii=False).encode()) > 4_000_000:
                raise RuntimeError('API tool context is full. Review the saved work before continuing in a new turn.')
            payload = {'model': model, 'stream': True, 'parallel_tool_calls': False}
            if responses:
                payload.update(instructions=instructions + GUIDANCE, input=conversation, tools=definitions,
                               store=False, include=['reasoning.encrypted_content'])
            else:
                payload.update(messages=[{'role':'system','content':instructions + GUIDANCE}, *conversation],
                               tools=[{'type':'function','function':{k:v for k,v in row.items() if k!='type'}} for row in definitions])
            text, output, calls = exchange(transport, payload, responses, on_delta)
            if not calls:
                if not text.strip(): raise RuntimeError('API did not return a completed answer.')
                outcome = "completed"
                return text.strip()
            if text:
                progress.commentary(str(uuid4()), text, True)
                transport.on_progress({'event': 'answer_reset'})
            conversation.extend(output)
            for call in calls:
                if transport.cancelled.is_set(): raise RuntimeError('API tool turn stopped.')
                identifier, name, raw = call['id'], call['name'], call['arguments']
                if not isinstance(identifier,str) or not identifier or identifier in seen or len(identifier)>256:
                    raise RuntimeError('Duplicate or invalid API tool call; nothing was retried.')
                seen.add(identifier)
                row = None
                try:
                    if not isinstance(raw,str) or len(raw)>32_000: raise ValueError('Invalid tool arguments.')
                    args = json.loads(raw)
                    validate_arguments(name,args)
                    row = {'id': str(uuid4()), 'kind': 'dynamicToolCall', 'tool': name, 'status': 'inProgress'}
                    # Persist only the catalog name and lifecycle. Arguments, credentials,
                    # returned page text and document contents never enter the tool journal.
                    transport.on_activity({'event': 'agent_activity', 'item': dict(row)})
                    progress.tool(row)
                    result = transport.workspace_tools.call(name,args)
                    # Image tool results are explicit multimodal context, not stringified base64.
                    image = result.get('image_url') if isinstance(result,dict) else None
                    metadata = {k:v for k,v in result.items() if k != 'image_url'} if image else result
                    result_text = json.dumps(metadata,ensure_ascii=False)
                    row['status'] = 'completed'
                except (ValueError,RuntimeError) as exc:
                    image = None
                    if row is not None: row['status'] = 'failed'
                    result_text = json.dumps({'error':str(exc)[:600],'retry_performed':False})
                if row is not None:
                    transport.on_activity({'event': 'agent_activity', 'item': dict(row)})
                    progress.tool(row)
                if responses:
                    content = [{'type':'input_text','text':result_text}, {'type':'input_image','image_url':image}] if image else result_text
                    conversation.append({'type':'function_call_output','call_id':identifier,'output':content})
                else:
                    conversation.append({'role':'tool','tool_call_id':identifier,'content':result_text})
                    if image: conversation.append({'role':'user','content':[{'type':'image_url','image_url':{'url':image}}]})
        raise RuntimeError('API tool turn stopped.')
    finally:
        progress.finish('interrupted' if transport.cancelled.is_set() else outcome)
        connection['key']=''


def exchange(transport, payload, responses, on_delta):
    url = urlsplit(transport.connection['endpoint'])
    path = url.path.rstrip('/') + ('/responses' if responses else '/chat/completions')
    headers = {'Content-Type':'application/json','Accept':'text/event-stream'}
    if transport.connection['key']: headers['Authorization']='Bearer '+transport.connection['key']
    transport.http = (http.client.HTTPSConnection(url.hostname,url.port,timeout=300,context=ssl.create_default_context())
                      if url.scheme=='https' else http.client.HTTPConnection(url.hostname,url.port,timeout=300))
    text, items, calls, finish, complete, count = [], [], {}, None, False, 0
    try:
        if transport.cancelled.is_set(): raise RuntimeError('API tool turn stopped.')
        transport.http.request('POST',path,body=json.dumps(payload,ensure_ascii=False).encode(),headers=headers)
        transport.stream_socket=transport.http.sock
        response=transport.http.getresponse()
        if response.status!=200: raise RuntimeError(f'API returned HTTP {response.status}. No retry or tool-mode fallback.')
        while True:
            if transport.cancelled.is_set(): raise RuntimeError('API tool turn stopped.')
            line=response.readline(1_048_577)
            if not line: break
            count+=len(line)
            if len(line)>1_048_576 or count>8_000_000: raise RuntimeError('API stream exceeds its buffer limit.')
            if not line.startswith(b'data:'): continue
            raw=line[5:].strip()
            if raw==b'[DONE]':
                complete=finish in {'stop','tool_calls'}
                break
            event=json.loads(raw)
            if not isinstance(event,dict) or 'error' in event: raise RuntimeError('API tool turn failed. No retry.')
            delta=''
            if responses:
                kind=event.get('type')
                if kind=='response.output_text.delta': delta=event.get('delta','')
                elif kind=='response.output_item.done':
                    item=event.get('item')
                    if not isinstance(item,dict): raise ValueError('Invalid output item')
                    items.append(item)
                elif kind=='response.completed':
                    result=event.get('response',{})
                    complete=result.get('status')=='completed'
                    if isinstance(result.get('output'),list): items=result['output']
                    break
                elif kind in {'error','response.failed','response.incomplete'}: raise RuntimeError('API tool turn did not complete. No retry.')
            else:
                choices=event.get('choices',[])
                if choices:
                    choice=choices[0]; fragment=choice.get('delta',{})
                    delta=fragment.get('content') or fragment.get('refusal') or ''
                    finish=choice.get('finish_reason') or finish
                    for fragment_call in fragment.get('tool_calls',[]):
                        index=fragment_call['index']
                        if type(index) is not int or not 0<=index<32: raise ValueError('Invalid call index')
                        call=calls.setdefault(index,{'id':'','name':'','arguments':''})
                        if fragment_call.get('id'):
                            if call['id'] and call['id']!=fragment_call['id']: raise ValueError('Changed call ID')
                            call['id']=fragment_call['id']
                        function=fragment_call.get('function',{})
                        call['name']+=function.get('name',''); call['arguments']+=function.get('arguments','')
                        if len(call['arguments'])>32_000: raise ValueError('Tool arguments too long')
            if not isinstance(delta,str): raise ValueError('Invalid text delta')
            if delta: text.append(delta); on_delta(delta)
        if transport.cancelled.is_set(): raise RuntimeError('API tool turn stopped.')
        if not complete: raise RuntimeError('API did not confirm completion. No tool was executed or retried.')
        if responses:
            parsed=[]
            for item in items:
                if item.get('type')=='function_call':
                    parsed.append({'id':item.get('call_id'),'name':item.get('name'),'arguments':item.get('arguments')})
                elif item.get('type') not in {'reasoning','message'}:
                    raise RuntimeError('Unsupported API tool type. No action was executed.')
            return ''.join(text),items,parsed
        parsed=[calls[k] for k in sorted(calls)]
        if parsed and finish!='tool_calls': raise RuntimeError('API did not complete its function calls.')
        message={'role':'assistant','content':''.join(text) or None}
        if parsed: message['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in parsed]
        return ''.join(text),[message],parsed
    except (OSError,http.client.HTTPException,ValueError,TypeError,AttributeError,KeyError):
        raise RuntimeError('API connection interrupted or tool format unsupported. No retry.') from None
    finally:
        transport.http.close(); transport.http=None; transport.stream_socket=None
