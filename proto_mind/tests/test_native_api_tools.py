import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from proto_mind.native_api import APITransport
from proto_mind.native_api_tools import exchange


class Calls:
    def __init__(self, result=None): self.calls = []; self.result = result or {"projects": []}
    def call(self, name, args): self.calls.append((name, args)); return self.result


class APIToolTests(unittest.TestCase):
    def transport(self, format="responses", endpoint="http://127.0.0.1:1/v1", result=None):
        transport = APITransport({"endpoint": endpoint, "key": "fixture-token", "format": format})
        transport.workspace_tools = Calls(result)
        return transport

    def test_responses_real_stream_preserves_reasoning_and_image_provenance(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
                if len(requests) == 1:
                    events = [{'type':'response.completed','response':{'status':'completed','output':[
                        {'type':'reasoning','id':'reason-1','summary':[], 'encrypted_content':'opaque'},
                        {'type':'function_call','id':'item-1','call_id':'call-1','name':'pm_browser_screenshot','arguments':'{"browser_id":"test"}'}]}}]
                else:
                    events = [{'type':'response.output_text.delta','delta':'Verified image'}, {'type':'response.completed','response':{'status':'completed','output':[]}}]
                for event in events: self.wfile.write(b'data: '+json.dumps(event).encode()+b'\n\n')
            def log_message(self,*_): pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        transport = self.transport(endpoint=f'http://127.0.0.1:{server.server_port}/v1', result={'image_url':'data:image/jpeg;base64,dGVzdA==','source_sha256':'source'})
        result = transport.answer('selected-model','instructions',[], 'show it',lambda _:None)
        self.assertEqual(result,'Verified image'); self.assertEqual(len(transport.workspace_tools.calls),1)
        self.assertEqual(requests[1]['input'][1]['encrypted_content'],'opaque')
        output = requests[1]['input'][-1]
        self.assertEqual(output['type'],'function_call_output'); self.assertEqual(output['call_id'],'call-1')
        self.assertEqual(output['output'][1]['type'],'input_image')
        self.assertIn('source',output['output'][0]['text'])
        self.assertEqual(transport.connection['key'],'')

    def test_duplicate_call_id_never_repeats_action(self):
        transport = self.transport()
        call = {'id':'same','name':'pm_list_projects','arguments':'{}'}
        with patch('proto_mind.native_api_tools.exchange', return_value=('',[],[call])) as request:
            with self.assertRaisesRegex(RuntimeError,'Duplicate'): transport.answer('m','i',[],'p',lambda _:None)
        self.assertEqual(len(transport.workspace_tools.calls),1); self.assertEqual(request.call_count,2)
        self.assertEqual(transport.connection['key'],'')

    def test_disconnected_followup_is_not_retried(self):
        transport = self.transport()
        events = []
        transport.on_activity = events.append
        first = ('',[],[{'id':'one','name':'pm_list_projects','arguments':'{}'}])
        with patch('proto_mind.native_api_tools.exchange', side_effect=[first,RuntimeError('disconnected')]) as request:
            with self.assertRaisesRegex(RuntimeError,'disconnected'): transport.answer('m','i',[],'p',lambda _:None)
        self.assertEqual(request.call_count,2); self.assertEqual(len(transport.workspace_tools.calls),1)
        self.assertEqual([e['item']['status'] for e in events], ['inProgress', 'completed'])
        self.assertEqual(set(events[0]['item']), {'id','kind','tool','status'})
        self.assertNotIn('fixture-token', json.dumps(events))

    def test_chat_completions_carries_tool_messages_and_schema(self):
        transport = self.transport('chat_completions')
        call = {'id':'one','name':'pm_list_projects','arguments':'{}'}
        message = {'role':'assistant','content':None,'tool_calls':[{'id':'one','type':'function','function':{'name':'pm_list_projects','arguments':'{}'}}]}
        payloads=[]
        def request(t,p,responses,delta):
            payloads.append(json.loads(json.dumps(p))); self.assertFalse(responses)
            return ('',[message],[call]) if len(payloads)==1 else ('Done',[],[])
        with patch('proto_mind.native_api_tools.exchange',side_effect=request): self.assertEqual(transport.answer('m','i',[],'p',lambda _:None),'Done')
        self.assertEqual(payloads[1]['messages'][-1]['role'],'tool')
        self.assertEqual(payloads[1]['messages'][-1]['tool_call_id'],'one')
        self.assertTrue(payloads[0]['tools'][0]['function']['strict'])

    def test_invalid_arguments_are_reported_without_invocation(self):
        transport = self.transport()
        events=[('',[],[{'id':'one','name':'pm_list_projects','arguments':'{"shell":"bad"}'}]),('Done',[],[])]
        with patch('proto_mind.native_api_tools.exchange',side_effect=events): transport.answer('m','i',[],'p',lambda _:None)
        self.assertEqual(transport.workspace_tools.calls,[])

    def test_cancel_before_dispatch_does_not_start_paid_request(self):
        transport = self.transport(); transport.cancel()
        with patch('proto_mind.native_api_tools.exchange') as request:
            with self.assertRaisesRegex(RuntimeError,'stopped'): transport.answer('m','i',[],'p',lambda _:None)
        request.assert_not_called(); self.assertEqual(transport.connection['key'],'')
