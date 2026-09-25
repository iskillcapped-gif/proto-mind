import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind.config import ProtoMindConfig
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_claude import ClaudeTransport, environment, status, authentication_command, profile_directory
from proto_mind.native_codex import TurnCancelled
from proto_mind.native_private_backup import NATIVE_ITEMS
from proto_mind.tests.test_native import FakeSubscription


class ClaudeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pm-claude-offline-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.runtime = self.root / 'runtime'
        package = self.runtime / 'claude_agent_sdk'
        package.mkdir(parents=True)
        shutil.copyfile(Path(__file__).with_name('claude_sdk_fixture.py'), package / '__init__.py')
        binary = package / '_bundled/claude'
        binary.parent.mkdir()
        binary.write_text('#!' + sys.executable + '\nimport json\nprint(json.dumps({"loggedIn": True, "email": "fixture@example.invalid", "token": "DO_NOT_EXPORT", "subscriptionType": "test"}))\n')
        binary.chmod(0o755)
        (self.runtime / 'proto-mind-claude-runtime.json').write_text('{}')
        runtime_patch = patch('proto_mind.native_claude.runtime_path', return_value=self.runtime)
        runtime_patch.start(); self.addCleanup(runtime_patch.stop)
        profile_directory(self.state, create=True)

    def transport(self, **values):
        transport = ClaudeTransport(self.state, workspace=None, full_access=False, **values)
        self.addCleanup(transport.cancel)
        return transport

    def test_environment_and_authentication_are_scoped_without_api_override(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY':'secret', 'CLAUDE_CODE_OAUTH_TOKEN':'secret',
                                   'ANTHROPIC_BASE_URL':'https://bad.invalid', 'CLAUDE_CONFIG_DIR':'/wrong',
                                   'PYTHONPATH':'/wrong', 'CLAUDE_CODE_USE_BEDROCK':'1'}):
            env = environment(self.state)
        self.assertEqual(env['CLAUDE_CONFIG_DIR'], str(self.state / 'claude-profile'))
        self.assertFalse(any(key.startswith('ANTHROPIC') for key in env))
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', env)
        self.assertNotIn('PYTHONPATH', env)
        command = authentication_command(self.state, 'login')
        self.assertEqual(command['arguments'], ['auth', 'login'])
        self.assertNotIn('token', status(self.state))
        self.assertEqual(status(self.state)['email'], 'fixture@example.invalid')
        self.assertNotIn('claude-profile', NATIVE_ITEMS)
        with self.assertRaises(ValueError): authentication_command(self.state, 'execute')

    def test_status_never_creates_a_profile(self):
        fresh = self.root / 'fresh'; fresh.mkdir()
        self.assertEqual(status(fresh), {'installed':True, 'connected':False})
        self.assertEqual(list(fresh.iterdir()), [])
        (fresh / 'claude-profile').symlink_to(self.state / 'claude-profile', target_is_directory=True)
        with self.assertRaises(ValueError): profile_directory(fresh, create=True)

    def test_plain_chat_streams_without_tools_and_preserves_explicit_context(self):
        transport = self.transport(effort='high')
        deltas = []
        answer = transport.answer('sonnet', 'PM memory', [{'role':'user','content':'previous'}], 'current', deltas.append)
        self.assertEqual(answer, 'Offline answer')
        self.assertEqual(deltas, ['Offline answer'])
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual(observed['tools'], [])
        self.assertEqual(observed['permission_mode'], 'dontAsk')
        self.assertEqual(observed['workspace_tools'], [])
        self.assertEqual(observed['effort'], 'high')
        self.assertIn('previous', observed['messages'][0]['message']['content'][0]['text'])
        self.assertEqual(observed['instructions']['append'], 'PM memory')

    def test_full_mac_workspace_roundtrip_and_commentary(self):
        transport = self.transport()
        transport.full_access = True
        class Calls:
            def __init__(self): self.calls = []
            def call(self, name, arguments): self.calls.append((name,arguments)); return {'projects': []}
            def cancel(self): pass
        calls = Calls(); transport.workspace_tools = calls
        events = []; transport.on_progress = events.append; transport.on_activity = events.append
        self.assertEqual(transport.answer('tools','instructions',[],'go',lambda _:None), 'Offline answer')
        self.assertEqual(calls.calls, [('pm_list_projects', {})])
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual(observed['permission_mode'], 'bypassPermissions')
        self.assertIn('pm_ask_user', observed['workspace_tools'])
        self.assertTrue(any(event.get('event') == 'answer_reset' for event in events))
        self.assertNotIn('PRIVATE THOUGHTS', json.dumps(events))
        self.assertEqual([event['item']['status'] for event in events if event.get('event') == 'agent_activity'], ['inProgress','completed'])

    def test_failed_disconnected_or_malformed_worker_is_never_success(self):
        for mode in ['failed','disconnect','malformed']:
            with self.subTest(mode=mode), self.assertRaises(RuntimeError) as error:
                self.transport().answer(mode,'instructions',[],'go',lambda _:None)
            self.assertNotIn('SECRET', str(error.exception))

    def test_auth_and_quota_errors_are_actionable_without_provider_diagnostics(self):
        errors = []
        for model in ['authentication_failed', 'rate_limit']:
            with self.assertRaises(RuntimeError) as error:
                self.transport().answer(model, 'instructions', [], 'go', lambda _: None)
            errors.append(str(error.exception))
        self.assertIn('войдите', errors[0])
        self.assertIn('лимит', errors[1])
        self.assertNotIn('SECRET', ' '.join(errors))

    def test_new_workers_resume_exact_saved_session_without_repeating_history(self):
        from proto_mind.native_claude_sessions import ClaudeSessionPlan
        conversation = str(uuid4())
        account = status(self.state)
        history = [{'role':'user', 'content':'Old context ' + 'x' * 6000}]
        def plan():
            return ClaudeSessionPlan(self.state, conversation, account=account, workspace=None,
                                     full_access=False, tools=False, history=history)
        original = plan()
        self.transport(session_plan=original).answer('sonnet', 'instructions', history, 'first', lambda _:None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual(observed['session_id'], original.session_id)
        self.assertIsNone(observed['resume'])
        self.assertIn('x' * 6000, observed['messages'][0]['message']['content'][0]['text'])
        history += [{'role':'assistant', 'content':'Offline answer'}]
        continued = plan()
        self.transport(session_plan=continued).answer('sonnet', 'instructions', history, 'second', lambda _:None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual(observed['resume'], original.session_id)
        self.assertIsNone(observed['session_id'])
        self.assertNotIn('Old context', observed['messages'][0]['message']['content'][0]['text'])

    def session_plan(self, conversation, history):
        from proto_mind.native_claude_sessions import ClaudeSessionPlan
        return ClaudeSessionPlan(self.state, conversation, account=status(self.state), workspace=None,
                                 full_access=False, tools=False, history=history)

    def test_usage_limit_keeps_the_session_for_the_next_user_turn_with_notice(self):
        conversation, history = str(uuid4()), [{'role':'user', 'content':'Start'}]
        original = self.session_plan(conversation, history)
        self.transport(session_plan=original).answer('sonnet', 'instructions', history, 'first', lambda _:None)
        history = history + [{'role':'assistant', 'content':'Offline answer'}]
        with self.assertRaises(RuntimeError) as error:
            self.transport(session_plan=self.session_plan(conversation, history)).answer(
                'rate_limit', 'instructions', history, 'second', lambda _:None)
        self.assertIn('продолжит эту же сессию', str(error.exception))
        continued = self.session_plan(conversation, history)
        self.assertTrue(continued.resumed and continued.interrupted)
        self.transport(session_plan=continued).answer('sonnet', 'instructions', history, 'third', lambda _:None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        text = observed['messages'][0]['message']['content'][0]['text']
        self.assertEqual(observed['resume'], original.session_id)
        self.assertIn('did not complete', text); self.assertIn('third', text)
        self.assertFalse(self.session_plan(conversation, history + [{'role':'assistant', 'content':'Offline answer'}]).interrupted)

    def test_missing_resumed_session_fails_once_then_starts_fresh(self):
        conversation, history = str(uuid4()), [{'role':'user', 'content':'Start'}]
        original = self.session_plan(conversation, history)
        self.transport(session_plan=original).answer('sonnet', 'instructions', history, 'first', lambda _:None)
        history = history + [{'role':'assistant', 'content':'Offline answer'}]
        continued = self.session_plan(conversation, history)
        self.assertTrue(continued.resumed)
        # Claude Code pruned the transcript after planning: resume fails before any model output.
        next((self.state / 'claude-profile/projects').glob('*/' + original.session_id + '.jsonl')).unlink()
        with self.assertRaises(RuntimeError):
            self.transport(session_plan=continued).answer('sonnet', 'instructions', history, 'second', lambda _:None)
        fresh = self.session_plan(conversation, history)
        self.assertFalse(fresh.resumed)
        self.assertEqual(self.transport(session_plan=fresh).answer('sonnet', 'instructions', history, 'third', lambda _:None), 'Offline answer')

    def test_completed_answer_survives_a_failed_continuation_update(self):
        conversation, history = str(uuid4()), []
        plan = self.session_plan(conversation, history)
        with patch.object(type(plan), 'complete', side_effect=ValueError('binding changed')):
            self.assertEqual(self.transport(session_plan=plan).answer('sonnet', 'instructions', history, 'go', lambda _:None), 'Offline answer')
        self.assertFalse(self.session_plan(conversation, [{'role':'user', 'content':'go'}, {'role':'assistant', 'content':'Offline answer'}]).resumed)

    def test_cancel_one_worker_leaves_a_different_turn_usable(self):
        transport = self.transport()
        errors = []
        def run():
            try: transport.answer('hang','instructions',[],'go',lambda _:None)
            except Exception as error: errors.append(error)
        thread = threading.Thread(target=run); thread.start()
        self.addCleanup(lambda: thread.join(timeout=5))
        deadline = time.monotonic() + 5
        while transport.process is None and time.monotonic() < deadline: time.sleep(.01)
        self.assertIsNotNone(transport.process)
        transport.cancel(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(errors[0], TurnCancelled)
        self.assertEqual(self.transport().answer('sonnet','instructions',[],'go',lambda _:None), 'Offline answer')

    def test_bridge_history_receipts_recall_and_access_are_claude_bound(self):
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        params = {'text':'Привет', 'provider':'claude', 'model':'sonnet', 'reasoning_effort':'medium',
                  'conversation_id':str(uuid4()), 'cloud_consent':True, 'auto_project_recall':True,
                  'project_recall_algorithm':'local_content_terms_v3'}
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            preview = backend.preview_context(params)
            self.assertEqual(preview['manifest']['destination'], 'anthropic_cloud')
            result = backend.process(params, lambda _:None, 'claude-chat')
            for key in ['instruction_receipt','turn_receipt']:
                self.assertEqual(result['work_session'][key]['provider'], 'claude')
            self.assertIsNone(result['provider_thread'])
            continued = {**params, 'text':'Continue', 'history':[{'role':'user','content':'Привет'},
                         {'role':'assistant','content':result['cognitive_turn']['response']}]}
            self.assertTrue(backend.preview_context(continued)['provider_thread']['linked'])
            next_result = backend.process(continued, lambda _:None, 'claude-resume')
            self.assertTrue(next_result['work_session']['context_manifest']['provider_thread']['linked'])
            self.assertEqual(next_result['work_session']['context_manifest']['history']['messages'], 0)
            self.assertEqual(backend.subscription.calls, [])
            with self.assertRaises(ValueError): backend.process({**params,'cloud_consent':False},lambda _:None,'no-consent')
            with self.assertRaises(ValueError): backend.process({**params,'access_mode':'full_access'},lambda _:None,'no-grant')
            workspace = self.root / 'workspace'; workspace.mkdir()
            grant = backend.dispatch('agent_access', {'conversation_id':params['conversation_id'], 'workspace_root':str(workspace), 'mode':'full_access', 'cloud_consent':True, 'confirmation':'ALLOW FULL MAC ACCESS'}, lambda _:None, 'grant')
            result = backend.process({**params,'workspace_root':str(workspace),'access_mode':'full_access','access_token':grant['token']},lambda _:None,'claude-agent')
            self.assertEqual(result['work_session']['instruction_receipt']['mode'], 'full_access')
            self.assertEqual(result['work_session']['status'], 'completed')


if __name__ == '__main__': unittest.main()
