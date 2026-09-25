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
    def __init__(self, *, options): self.options = options
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def query(self, prompt):
        assert hasattr(prompt, '__aiter__'), 'SDK requires an async iterable, not a dict'
        messages = [item async for item in prompt]
        assert len(messages) == 1 and messages[0]['message']['role'] == 'user'
        self.content = messages[0]['message']['content']
        options = self.options
        assert options.setting_sources == [] and options.strict_mcp_config is True
        assert options.extra_args == {'no-session-persistence': None}
        full = options.permission_mode == 'bypassPermissions'
        assert options.tools == ({'type':'preset','preset':'claude_code'} if full else [])
        Path(options.cwd, 'sdk-observed.json').write_text(json.dumps({
            'permission_mode': options.permission_mode, 'tools': options.tools,
            'model': options.model, 'effort': options.effort,
            'messages': messages, 'instructions': options.system_prompt,
            'workspace_tools': [item.name for item in options.mcp_servers.get('pm',{}).get('tools',[])]
        }))
    async def receive_response(self):
        mode = self.options.model
        if mode == 'hang': await asyncio.Event().wait()
        if mode == 'malformed': raise RuntimeError('SECRET THAT MUST NEVER REACH PM')
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
        yield ResultMessage(is_error=mode == 'failed', subtype='error' if mode == 'failed' else 'success', result='Offline answer')
