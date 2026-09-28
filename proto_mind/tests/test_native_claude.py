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
from uuid import UUID, uuid4

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
        # A read screenshot arrives as one JSON line; 1 MiB once ended a turn.
        self.assertGreaterEqual(observed['max_buffer_size'], 32 * 1024 * 1024)

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

    def test_turn_usage_counts_each_request_once_and_becomes_an_answer_notice(self):
        from proto_mind.native_claude import usage_notice
        transport = self.transport()
        self.assertEqual(transport.answer('usage', 'instructions', [], 'go', lambda _: None), 'Offline answer')
        # Per-turn counts come from each request, not from session-cumulative result totals.
        self.assertEqual(transport.usage, {'requests': 2, 'subagent_requests': 1, 'context_max': 21502, 'input_tokens': 10,
                                           'cache_creation_input_tokens': 5500, 'cache_read_input_tokens': 41000,
                                           'output_tokens': 390, 'thinking_tokens': 200})
        notice = usage_notice(transport.usage)
        self.assertTrue(notice.startswith('Claude usage for this turn: 2 model requests plus 1 by subagents, context up to 22K tokens.'))
        self.assertIn('read from cache 41K', notice)
        self.assertIn('output 390 including 200 thinking', notice)
        self.assertIsNone(self.transport().usage)
        for invalid in [None, {}, {**transport.usage, 'requests': 0}, {**transport.usage, 'extra': 1}, {**transport.usage, 'output_tokens': -1}]:
            self.assertIsNone(usage_notice(invalid))
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            result = backend.process({'text': 'Привет', 'provider': 'claude', 'model': 'usage', 'conversation_id': str(uuid4()),
                                      'cloud_consent': True}, lambda _: None, 'usage')
        self.assertIn(notice, result['notices'])

    def test_updates_reach_the_running_turn_or_the_follow_up_it_waits_for(self):
        for model, expected in [('steer', 'Done; Also check the README'), ('steer-late', 'second answer: Also check the README')]:
            with self.subTest(model=model):
                transport = self.transport()
                ready, targets, events, result = threading.Event(), [], [], {}
                transport.on_steering = lambda target: (targets.append(target), ready.set())
                transport.on_progress = events.append
                worker = threading.Thread(target=lambda: result.update(answer=transport.answer(model, 'instructions', [], 'go', lambda _: None)))
                worker.start()
                self.assertTrue(ready.wait(10))
                self.assertEqual(transport.steer(str(uuid4()), 'Also check the README'), 'accepted')
                worker.join(20)
                self.assertEqual(result.get('answer'), expected)
                self.assertEqual(targets, [transport, None])
                self.assertEqual(transport.steer(str(uuid4()), 'Too late'), 'rejected')
                self.assertEqual(transport.undelivered_updates, [])
                # A late update's answer comes last; the earlier answer stays visible as progress.
                self.assertEqual(any(event.get('event') == 'answer_reset' for event in events), model == 'steer-late')

    def test_live_steering_routes_claude_updates_and_closes_with_the_turn(self):
        from proto_mind.native_steering import LiveSteering
        conversation, emitted = str(uuid4()), []
        steering = LiveSteering('request-1', conversation, emitted.append)
        class Target:
            calls = []
            def steer(self, identifier, text, images): self.calls.append((identifier, text, images)); return 'accepted'
        target = Target()
        steering.set_active(('claude', 'request-1'), target)
        token = emitted[-1]['token']
        params = lambda message: {'request_id': 'request-1', 'conversation_id': conversation, 'token': token,
                                  'message_id': message, 'text': 'Add the missing test', 'cloud_consent': True}
        first = str(uuid4())
        self.assertEqual(steering.send(params(first))['status'], 'accepted')
        self.assertEqual(target.calls, [(first, 'Add the missing test', [])])
        steering.set_active(None)
        self.assertIsNone(emitted[-1]['token'])
        self.assertEqual(steering.send(params(str(uuid4())))['status'], 'rejected')
        self.assertEqual(len(target.calls), 1)

    def test_bridge_offers_claude_updates_during_a_turn(self):
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        conversation, ready, result = str(uuid4()), threading.Event(), {}
        tokens = []
        def emit(event):
            if event.get('event') == 'steering_ready' and event.get('token'): tokens.append(event['token']); ready.set()
        params = {'text': 'Привет', 'provider': 'claude', 'model': 'steer', 'conversation_id': conversation, 'cloud_consent': True}
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            worker = threading.Thread(target=lambda: result.update(turn=backend.process(params, emit, 'steer-request')))
            worker.start()
            self.assertTrue(ready.wait(15))
            receipt = backend.dispatch('steer', {'request_id': 'steer-request', 'conversation_id': conversation, 'token': tokens[-1],
                                                 'message_id': str(uuid4()), 'text': 'Also check the README', 'cloud_consent': True},
                                       lambda _: None, 'steer-rpc')
            worker.join(20)
        self.assertEqual(receipt['status'], 'accepted')
        self.assertIn('Also check the README', result['turn']['cognitive_turn']['response'])

    def test_claude_tool_calls_become_readable_actions_and_a_saved_receipt(self):
        transport = self.transport()
        transport.full_access = True
        events = []
        transport.on_activity = events.append
        self.assertEqual(transport.answer('claude-tools', 'instructions', [], 'go', lambda _: None), 'Done')
        rows = {event['item']['id']: event['item'] for event in events if event.get('event') == 'agent_activity'}
        self.assertEqual({key: row['kind'] for key, row in rows.items()},
                         {'bash-1': 'commandExecution', 'edit-1': 'fileChange', 'read-1': 'fileRead', 'grep-1': 'search'})
        self.assertEqual((rows['bash-1']['command'], rows['bash-1']['text'], rows['bash-1']['output_preview'], rows['bash-1']['status']),
                         ('pytest -q', 'Run the tests', '3 passed in 0.1s', 'completed'))
        self.assertIsInstance(rows['bash-1']['duration_ms'], int)
        self.assertEqual(rows['edit-1']['file_changes'], [{'path': '/tmp/demo.py', 'additions': 2, 'deletions': 1}])
        self.assertEqual(rows['edit-1']['diff_preview'], '- a = 1\n+ a = 2\n+ b = 3')
        self.assertEqual((rows['grep-1']['query'], rows['grep-1']['path']), ('TODO', '/tmp'))
        # A read file's contents are not repeated into PM's activity or receipt.
        self.assertNotIn('PRIVATE FILE BODY', json.dumps(events))
        receipt = [event['receipt'] for event in events if event.get('event') == 'agent_run'][-1]
        self.assertEqual((receipt['schema'], receipt['status'], receipt['command_count'], len(receipt['items'])),
                         ('proto_mind.claude_agent_run.v1', 'completed', 1, 4))
        self.assertTrue(receipt['execution_may_have_occurred'])
        self.assertEqual(receipt['workspace_root'], '')
        self.assertEqual(self.transport().tool_rows, {})
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            result = backend.process({'text': 'Привет', 'provider': 'claude', 'model': 'claude-tools', 'conversation_id': str(uuid4()),
                                      'cloud_consent': True}, lambda _: None, 'tools-request')
        self.assertEqual([item['kind'] for item in result['agent_run']['items']], ['commandExecution', 'fileChange', 'fileRead', 'search'])
        self.assertEqual([item['kind'] for item in result['work_session']['tools']], ['commandExecution', 'fileChange', 'fileRead', 'search'])
        self.assertEqual([entry['tool_kind'] for entry in result['work_log']['entries'] if entry['kind'] == 'tool'],
                         ['commandExecution', 'fileChange', 'fileRead', 'search'])

    def test_changed_line_counts_are_exact_and_cover_a_long_turn(self):
        transport = self.transport()
        transport.full_access = True
        events = []
        transport.on_activity = events.append
        self.assertEqual(transport.answer('claude-edit-counts', 'instructions', [], 'go', lambda _: None), 'Done')
        receipt = [event['receipt'] for event in events if event.get('event') == 'agent_run'][-1]
        edits = {item['id']: item for item in receipt['items'] if item['kind'] == 'fileChange'}
        # The patch counts only changed lines; a created file has no deletions; a rewrite's deletions are known.
        self.assertEqual({key: item['file_changes'] for key, item in edits.items()}, {
            'edit-1': [{'path': '/tmp/app.py', 'additions': 1, 'deletions': 1}],
            'write-new': [{'path': '/tmp/new.md', 'additions': 4, 'deletions': 0}],
            'write-over': [{'path': '/tmp/old.md', 'additions': 2, 'deletions': 5}]})
        # Only the latest 64 actions stay whole, but every edit stays, without its diff.
        self.assertTrue(receipt['items_truncated'] and receipt['file_changes_complete'])
        self.assertEqual(len(receipt['items']), 3 + 64)
        self.assertFalse(any('diff_preview' in item for item in edits.values()))

    def test_claude_code_compaction_is_one_work_log_row_with_its_counts(self):
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        events = []
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            result = backend.process({'text': 'Привет', 'provider': 'claude', 'model': 'compact', 'conversation_id': str(uuid4()),
                                      'cloud_consent': True}, events.append, 'compact-request')
        self.assertEqual(result['cognitive_turn']['response'], 'Done')
        live = [entry for event in events if event.get('event') == 'work_log' for entry in event['log']['entries']
                if entry['kind'] == 'context_compaction']
        self.assertEqual([entry['status'] for entry in live][:1], ['inProgress'])
        self.assertEqual(len({entry['id'] for entry in live}), 1)  # Repeated status updates keep one row.
        for log in (result['work_log'], result['work_session']['work_log']):
            rows = [entry for entry in log['entries'] if entry['kind'] == 'context_compaction']
            self.assertEqual([(row['status'], row['pre_tokens'], row['post_tokens'], row['duration_ms']) for row in rows],
                             [('completed', 968276, 14805, 93480)])
        self.assertNotIn('PRIVATE CONTEXT', json.dumps([events, result], ensure_ascii=False))

    def test_computer_use_tools_are_claude_full_mac_only_and_keep_the_system_prompt(self):
        from proto_mind.native_workspace_tools import COMPUTER_TOOLS, GUIDANCE, WorkspaceTools
        from proto_mind.native_claude_contract import instructions
        click = {'action': 'click', 'x': 620, 'y': 430, 'x2': None, 'y2': None, 'amount': None, 'text': None, 'direction': None, 'capture': None}
        with self.assertRaises(ValueError):
            WorkspaceTools('r', str(uuid4()), lambda _: None).call('pm_computer_action', click)
        tools = WorkspaceTools('r', str(uuid4()), lambda _: None, timeout=0.2, computer_use=True)
        for invalid in [{**click, 'x': '620'}, {**click, 'action': 'shell'}, {**click, 'x': 10**7}, {'action': 'click'}]:
            with self.subTest(arguments=invalid), self.assertRaises(ValueError):
                tools.call('pm_computer_action', invalid)
        with self.assertRaises(RuntimeError):  # Valid arguments reach Native; nothing answers in this test.
            tools.call('pm_computer_action', click)
        from proto_mind.native_claude_protocol import tool_row
        typed = tool_row('t', 'mcp__pm__pm_computer_action', {**click, 'action': 'type', 'text': 'secret words'})
        self.assertEqual((typed['kind'], typed['tool']), ('computerUse', 'type_text'))
        self.assertNotIn('secret words', json.dumps(typed))  # Typed text and coordinates stay out of PM's journal.
        self.assertEqual(tool_row('s', 'mcp__pm__pm_screen_capture', {'app': 'Safari'})['app'], 'Safari')
        self.assertEqual(tool_row('z', 'mcp__pm__pm_screen_zoom', {'region': [0, 0, 300, 120]})['tool'], 'zoom')
        # A long-lived session may keep an older schema copy: calls without the newer optional fields still work.
        with self.assertRaises(RuntimeError):
            tools.call('pm_computer_action', {key: value for key, value in click.items() if key not in {'direction', 'capture'}})
        # Like Anthropic's computer-use toolset: batches, zoom regions, scroll directions and a capture after actions.
        step = {key: value for key, value in click.items() if key != 'capture'}
        batch = {'steps': [step, {**step, 'action': 'type', 'x': None, 'y': None, 'text': 'secret words'},
                           {**step, 'action': 'key', 'x': None, 'y': None, 'text': 'Return', 'amount': 2}], 'capture': True}
        with self.assertRaises(RuntimeError):  # Valid: it reaches Native.
            tools.call('pm_computer_batch', batch)
        for name, invalid in [('pm_computer_batch', {'steps': [], 'capture': None}), ('pm_computer_batch', {'steps': [step] * 17, 'capture': None}),
                              ('pm_computer_batch', {'steps': [{**step, 'capture': True}], 'capture': None}),
                              ('pm_computer_batch', {'steps': [{**step, 'action': 'shell'}], 'capture': None}),
                              ('pm_computer_action', {**click, 'direction': 'diagonal'}), ('pm_computer_action', {**click, 'capture': 'yes'}),
                              ('pm_screen_zoom', {'region': [0, 0, 300]}), ('pm_screen_zoom', {'region': [0, 0, 1.5, 3]}),
                              ('pm_screen_zoom', {'region': None}), ('pm_screen_capture', {'app': None, 'region': [0, 0, 5, 5]})]:
            with self.subTest(tool=name, arguments=invalid), self.assertRaises(ValueError):
                tools.call(name, invalid)
        row = tool_row('b', 'mcp__pm__pm_computer_batch', batch)
        self.assertEqual((row['kind'], row['tool'], row['note']), ('computerUse', 'batch', 'click · type_text · press_key'))
        self.assertNotIn('secret words', json.dumps(row))
        self.assertNotIn('pm_computer_action', GUIDANCE)
        self.assertEqual(instructions(full_access=True, workspace_tools=True).count('Workspace tool catalog'), 1)
        class Calls:
            def call(self, name, arguments): return {'projects': []}
            def cancel(self): pass
        full, chat = self.transport(), self.transport()
        full.full_access = True
        full.workspace_tools = Calls()
        full.answer('tools', 'instructions', [], 'go', lambda _: None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertTrue({row['name'] for row in COMPUTER_TOOLS} <= set(observed['workspace_tools']))
        chat.workspace_tools = Calls()
        chat.answer('sonnet', 'instructions', [], 'go', lambda _: None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertFalse({row['name'] for row in COMPUTER_TOOLS} & set(observed['workspace_tools']))

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

    def test_a_resumed_session_continues_exactly_after_the_last_answer(self):
        conversation = str(uuid4())
        history = [{'role': 'user', 'content': 'first'}]
        first = self.session_plan(conversation, history)
        self.transport(session_plan=first).answer('sonnet', 'instructions', history, 'first', lambda _: None)
        leaf = json.loads(first.leaf_path.read_text())
        self.assertEqual((leaf['session_id'], str(UUID(leaf['leaf']))), (first.session_id, leaf['leaf']))
        history += [{'role': 'assistant', 'content': 'Offline answer'}]
        second = self.session_plan(conversation, history)
        self.assertEqual(second.resume_at, leaf['leaf'])
        self.transport(session_plan=second).answer('sonnet', 'instructions', history, 'second', lambda _: None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual((observed['resume'], observed['resume_session_at']), (first.session_id, leaf['leaf']))
        # A leaf that belongs to another answer is ignored; the session still resumes plainly.
        stale = json.loads(second.leaf_path.read_text()); stale['answer_hash'] = 'f' * 64
        second.leaf_path.write_text(json.dumps(stale))
        history += [{'role': 'user', 'content': 'second'}, {'role': 'assistant', 'content': 'Offline answer'}]
        third = self.session_plan(conversation, history)
        self.assertTrue(third.resumed)
        self.assertIsNone(third.resume_at)
        # An interrupted turn resumes plainly so the model sees what it had already done.
        with self.assertRaises(RuntimeError):
            self.transport(session_plan=third).answer('rate_limit', 'instructions', history, 'third', lambda _: None)
        interrupted = self.session_plan(conversation, history + [{'role': 'user', 'content': '[Proto-Mind: this request did not complete (stopped, usage limit or error) and has no confirmed answer. Its actions may be partial; do not repeat them unless the current request asks.]\nthird'}])
        self.assertTrue(interrupted.interrupted)
        self.assertIsNone(interrupted.resume_at)

    def test_resume_continues_after_an_answer_written_before_its_parent(self):
        # Claude Code sometimes writes an answer's deferred_tools_record parent after the answer and
        # records that parent as the leaf. Resuming at the answer then failed before any model call
        # (twice on 2026-09-27), and the next message began a fresh session from local history.
        (self.state / 'claude-profile/transcript-mode').write_text('late-parent')
        conversation, history = str(uuid4()), [{'role': 'user', 'content': 'first'}]
        first = self.session_plan(conversation, history)
        self.transport(session_plan=first).answer('sonnet', 'instructions', history, 'first', lambda _: None)
        leaf = json.loads(first.leaf_path.read_text())['leaf']
        history += [{'role': 'assistant', 'content': 'Offline answer'}]
        self.assertEqual(self.transport(session_plan=self.session_plan(conversation, history)).answer(
            'sonnet', 'instructions', history, 'second', lambda _: None), 'Offline answer')
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual((observed['resume'], observed['resume_session_at']), (first.session_id, leaf))
        transcript = next((self.state / 'claude-profile/projects').glob('*/' + first.session_id + '.jsonl'))
        pins = [entry for entry in map(json.loads, transcript.read_text().splitlines()) if entry.get('explicit')]
        self.assertEqual(pins, [{'type': 'last-prompt', 'leafUuid': leaf, 'explicit': True, 'sessionId': first.session_id}])

    def test_a_refused_resume_point_keeps_the_session_for_the_next_message(self):
        from proto_mind.native_claude_sessions import INCOMPLETE_REQUEST
        conversation, history = str(uuid4()), [{'role': 'user', 'content': 'first'}]
        first = self.session_plan(conversation, history)
        self.transport(session_plan=first).answer('sonnet', 'instructions', history, 'first', lambda _: None)
        history += [{'role': 'assistant', 'content': 'Offline answer'}]
        (self.state / 'claude-profile/transcript-mode').write_text('reject-resume-point')
        with self.assertRaises(RuntimeError) as error:
            self.transport(session_plan=self.session_plan(conversation, history)).answer(
                'sonnet', 'instructions', history, 'second', lambda _: None)
        self.assertIn('точку продолжения', str(error.exception))
        # Nothing reached the model: the same session continues from Claude Code's own point.
        history += [{'role': 'user', 'content': INCOMPLETE_REQUEST + 'second'}]
        continued = self.session_plan(conversation, history)
        self.assertTrue(continued.resumed and continued.interrupted)
        self.assertIsNone(continued.resume_at)
        self.transport(session_plan=continued).answer('sonnet', 'instructions', history, 'third', lambda _: None)
        observed = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        self.assertEqual((observed['resume'], observed['resume_session_at']), (first.session_id, None))

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

    def test_failed_request_stays_in_history_and_still_resumes_or_bootstraps(self):
        from proto_mind.native_claude_sessions import ClaudeSessionPlan, INCOMPLETE_REQUEST
        conversation, history = str(uuid4()), [{'role':'user', 'content':'Start'}]
        self.transport(session_plan=self.session_plan(conversation, history)).answer('sonnet', 'instructions', history, 'first', lambda _:None)
        history = history + [{'role':'assistant', 'content':'Offline answer'}]
        with self.assertRaises(RuntimeError):
            self.transport(session_plan=self.session_plan(conversation, history)).answer(
                'rate_limit', 'instructions', history, 'Refactor the parser', lambda _:None)
        # Native keeps the failed request after the last answer, with its marker.
        history = history + [{'role':'user', 'content':INCOMPLETE_REQUEST + 'Refactor the parser'}]
        continued = self.session_plan(conversation, history)
        self.assertTrue(continued.resumed and continued.interrupted)
        self.assertEqual(continued.history, [])
        # A session that cannot continue (here: a changed system prompt) still sees the request.
        fresh = ClaudeSessionPlan(self.state, conversation, account=status(self.state), workspace=None,
                                  full_access=False, tools=False, history=history, contract='changed-system-prompt')
        self.assertFalse(fresh.resumed)
        self.transport(session_plan=fresh).answer('sonnet', 'instructions', history, 'continue', lambda _:None)
        text = json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())['messages'][0]['message']['content'][0]['text']
        self.assertIn('this request did not complete', text); self.assertIn('Refactor the parser', text)

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

    def test_resumed_session_keeps_its_system_prompt_and_receives_current_turn_context(self):
        from proto_mind.native_instructions import claude_session_contract, claude_system_text
        root = self.root / 'project'
        backend = NativeBackend(root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(backend.close)
        params = {'text':'Привет', 'provider':'claude', 'model':'sonnet', 'reasoning_effort':'medium',
                  'conversation_id':str(uuid4()), 'cloud_consent':True}
        observed = lambda: json.loads((self.state / 'claude-profile/sdk-observed.json').read_text())
        question = 'Что ты помнишь о моих предпочтениях?'
        with patch.object(ProtoMindConfig, 'from_env', return_value=ProtoMindConfig(data_dir=root / 'proto_mind/data')):
            first = backend.process(params, lambda _:None, 'first')
            opening = observed()
            backend.process({**params, 'text':question, 'history':[{'role':'user','content':'Привет'},
                             {'role':'assistant','content':first['cognitive_turn']['response']}]}, lambda _:None, 'second')
            resumed = observed()
        self.assertEqual(resumed['resume'], opening['session_id'])
        self.assertEqual(opening['instructions']['append'], claude_system_text(full_access=False, workspace_tools=False))
        self.assertEqual(resumed['instructions'], opening['instructions'])
        texts = [value['messages'][0]['message']['content'][0]['text'] for value in (opening, resumed)]
        self.assertIn('query_type: new_question', texts[0])
        self.assertIn('query_type: memory_inventory', texts[1])
        self.assertLess(texts[1].index('</proto_mind_turn_context>'), texts[1].index(question))
        binding = json.loads((self.state / 'claude_sessions' / (params['conversation_id'] + '.json')).read_text())['binding']
        self.assertEqual(binding['contract'], claude_session_contract(full_access=False, workspace_tools=False))

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
