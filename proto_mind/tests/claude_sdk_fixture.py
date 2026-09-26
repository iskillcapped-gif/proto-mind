"""Offline substitute imported ONLY by disposable Claude worker tests."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

class ClaudeAgentOptions(SimpleNamespace): pass
class SdkMcpTool(SimpleNamespace): pass
class AssistantMessage(SimpleNamespace): pass
class UserMessage(SimpleNamespace): pass
class StreamEvent(SimpleNamespace): pass
class ResultMessage(SimpleNamespace): pass
class TextBlock(SimpleNamespace): pass
class ToolUseBlock(SimpleNamespace): pass
class ToolResultBlock(SimpleNamespace): pass

def create_sdk_mcp_server(**values): return values

class ClaudeSDKClient:
    def __init__(self, *, options): self.options = options; self._query = self
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def get_server_info(self):
        return {'models': [
            {'value':'default', 'resolvedModel':'claude-opus-5-5', 'displayName':'Default', 'description':'Opus 5.5', 'supportsEffort':True, 'supportedEffortLevels':['low','high']},
            {'value':'opus', 'resolvedModel':'claude-opus-5-5', 'displayName':'Opus', 'description':'Opus 5.5', 'supportsEffort':True, 'supportedEffortLevels':['low','high']},
            {'value':'haiku', 'resolvedModel':'claude-haiku-4-5-20251001', 'displayName':'Haiku'}
        ], 'credential':'SECRET_NOT_METADATA'}
    async def _send_control_request(self, request):
        assert request == {'subtype':'get_usage'}
        assert self.options.tools == [] and self.options.permission_mode == 'dontAsk'
        assert self.options.strict_mcp_config and self.options.setting_sources == []
        mode = Path(self.options.cwd, 'metadata-mode')
        mode = mode.read_text() if mode.exists() else ''
        if mode == 'hang': await asyncio.Event().wait()
        if mode == 'unsupported': raise RuntimeError('SECRET unsupported control message')
        return {'rate_limits_available':True, 'rate_limits': {
            'five_hour':{'utilization':3,'resets_at':'2030-09-25T20:00:00+00:00'},
            'seven_day':{'utilization':0,'resets_at':'2030-09-30T20:00:00Z'},
            'extra_usage':{'is_enabled':False}, 'secret':'SECRET_NOT_METADATA'},
            'session':{'transcript':'SECRET_NOT_METADATA'}}
    async def query(self, prompt):
        assert hasattr(prompt, '__aiter__'), 'SDK requires an async iterable, not a dict'
        messages = [item async for item in prompt]
        if hasattr(self, 'content'):
            # Like streaming input: a later query during the turn is an operator update.
            assert len(messages) == 1 and messages[0]['uuid'] and messages[0]['message']['role'] == 'user'
            self.updates.extend(messages); self.updated.set(); return
        self.updates, self.updated = [], asyncio.Event()
        assert len(messages) == 1 and messages[0]['message']['role'] == 'user'
        self.content = messages[0]['message']['content']
        options = self.options
        assert options.setting_sources == [] and options.strict_mcp_config is True
        assert options.extra_args == {'replay-user-messages': None, **({} if options.session_id or options.resume else {'no-session-persistence': None})}
        # Like Claude Code: persisted sessions live in projects/<cwd>/<id>.jsonl,
        # and an explicit resume of a missing transcript fails before any model call.
        session = options.resume or options.session_id
        if session:
            import os
            transcript = Path(os.environ['CLAUDE_CONFIG_DIR'], 'projects', 'fixture', session + '.jsonl')
            if options.resume and not transcript.exists():
                raise RuntimeError('No conversation found with session ID: ' + session)
            transcript.parent.mkdir(parents=True, exist_ok=True)
            with transcript.open('a') as stream: stream.write(json.dumps({'type': 'user'}) + '\n')
        full = options.permission_mode == 'bypassPermissions'
        assert options.tools == ({'type':'preset','preset':'claude_code'} if full else [])
        Path(options.cwd, 'sdk-observed.json').write_text(json.dumps({
            'permission_mode': options.permission_mode, 'tools': options.tools,
            'model': options.model, 'effort': options.effort,
            'session_id': options.session_id, 'resume': options.resume,
            'messages': messages, 'instructions': options.system_prompt,
            'workspace_tools': [item.name for item in options.mcp_servers.get('pm',{}).get('tools',[])]
        }))
    async def receive_messages(self):
        mode = self.options.model
        session = self.options.resume or self.options.session_id
        def answer(text):
            return [StreamEvent(event={'type':'content_block_delta','delta':{'type':'text_delta','text':text}}),
                    AssistantMessage(content=[TextBlock(text=text)])]
        if mode == 'steer':
            # The update arrives while a tool runs and is added before the next request.
            yield AssistantMessage(content=[ToolUseBlock(id='bash-1', name='Bash')])
            await asyncio.wait_for(self.updated.wait(), 10)
            update = self.updates[-1]
            yield UserMessage(content=[ToolResultBlock(tool_use_id='bash-1', is_error=False)])
            yield UserMessage(content=update['message']['content'], uuid=update['uuid'])
            for message in answer('Done; ' + update['message']['content'][0]['text']): yield message
            yield ResultMessage(is_error=False, subtype='success', result='Done; ' + update['message']['content'][0]['text'], session_id=session)
            return
        if mode == 'steer-late':
            # The model already answered; Claude Code runs the update as the next turn.
            for message in answer('first answer'): yield message
            await asyncio.wait_for(self.updated.wait(), 10)
            yield ResultMessage(is_error=False, subtype='success', result='first answer', session_id=session)
            update = self.updates[-1]
            yield UserMessage(content=update['message']['content'], uuid=update['uuid'])
            for message in answer('second answer: ' + update['message']['content'][0]['text']): yield message
            yield ResultMessage(is_error=False, subtype='success', result='second answer: ' + update['message']['content'][0]['text'], session_id=session)
            return
        async for message in self.receive_response():
            yield message

    async def receive_response(self):
        mode = self.options.model
        if mode == 'hang': await asyncio.Event().wait()
        if mode == 'malformed': raise RuntimeError('SECRET THAT MUST NEVER REACH PM')
        if mode in {'rate_limit', 'authentication_failed'}:
            yield AssistantMessage(content=[], error=mode)
            yield ResultMessage(is_error=True, subtype='success', result=None,
                                api_error_status=429 if mode=='rate_limit' else 401)
            return
        if mode == 'usage':
            # Two main requests and one subagent request; streamed deltas carry the final output counts.
            opening = {'input_tokens':5, 'cache_creation_input_tokens':1000, 'cache_read_input_tokens':20000, 'output_tokens':1}
            yield StreamEvent(event={'type':'message_start','message':{'id':'msg-1','usage':opening}})
            yield AssistantMessage(content=[ToolUseBlock(id='call-u', name='Read')], message_id='msg-1', usage=opening)
            yield StreamEvent(event={'type':'message_delta','usage':{'output_tokens':300,'output_tokens_details':{'thinking_tokens':200}}})
            yield AssistantMessage(content=[TextBlock(text='nested')], parent_tool_use_id='call-u', message_id='msg-sub',
                                   usage={'input_tokens':3, 'cache_creation_input_tokens':4000, 'cache_read_input_tokens':0, 'output_tokens':50})
            closing = {'input_tokens':2, 'cache_creation_input_tokens':500, 'cache_read_input_tokens':21000, 'output_tokens':1}
            yield StreamEvent(event={'type':'message_start','message':{'id':'msg-2','usage':closing}})
            yield StreamEvent(event={'type':'content_block_delta','delta':{'type':'text_delta','text':'Offline answer'}})
            yield AssistantMessage(content=[TextBlock(text='Offline answer')], message_id='msg-2', usage=closing)
            yield StreamEvent(event={'type':'message_delta','usage':{'output_tokens':40}})
            yield ResultMessage(is_error=False, subtype='success', result='Offline answer', session_id=self.options.resume or self.options.session_id,
                                usage={'cache_read_input_tokens':99_000_000}, total_cost_usd=123.0)
            return
        if mode == 'tools':
            yield StreamEvent(event={'type':'content_block_delta','delta':{'type':'text_delta','text':'Checking projects'}})
            yield AssistantMessage(content=[TextBlock(text='Checking projects'), ToolUseBlock(id='call-1', name='mcp__pm__pm_list_projects')])
            handler = next(item.handler for item in self.options.mcp_servers['pm']['tools'] if item.name == 'pm_list_projects')
            result = await handler({})
            assert result['content'][0]['type'] == 'text'
            yield UserMessage(content=[ToolResultBlock(tool_use_id='call-1', is_error=False)])
        yield StreamEvent(event={'type':'content_block_delta','delta':{'type':'thinking_delta','thinking':'PRIVATE THOUGHTS'}})
        yield StreamEvent(event={'type':'content_block_delta','delta':{'type':'text_delta','text':'Offline answer'}})
        yield AssistantMessage(content=[TextBlock(text='Offline answer')])
        if mode == 'disconnect': return
        yield ResultMessage(is_error=mode == 'failed', subtype='error' if mode == 'failed' else 'success', result='Offline answer',
                            session_id=self.options.resume or self.options.session_id)
