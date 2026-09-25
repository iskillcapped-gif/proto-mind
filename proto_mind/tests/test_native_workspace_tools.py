from concurrent.futures import ThreadPoolExecutor
import json
import os
import queue
import threading
import unittest

from proto_mind.native_workspace_tools import WorkspaceTools, TOOLS, validate_arguments


class WorkspaceToolChannelTests(unittest.TestCase):
    def setUp(self):
        self.event = threading.Event()
        self.events = []
        def emit(value):
            self.events.append(value); self.event.set()
        self.channel = WorkspaceTools('turn-a', 'conversation-a', emit, timeout=.5)
        self.pool = ThreadPoolExecutor(1)
        self.addCleanup(self.pool.shutdown)
        self.addCleanup(self.channel.cancel)

    def reply(self, **changes):
        return dict(request_id='turn-a', call_id=self.events[-1]['call_id'], success=True,
                    result={'tasks': []}, error='', **changes)

    def test_reply_uses_exact_turn_and_call_once(self):
        future = self.pool.submit(self.channel.call, 'pm_list_tasks', {})
        self.assertTrue(self.event.wait(1))
        reply = self.reply()
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.channel.resolve({**reply, 'request_id': 'turn-b'})
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.channel.resolve({**reply, 'call_id': 'unknown'})
        self.channel.resolve(reply)
        self.assertEqual(future.result(1), {'tasks': []})
        with self.assertRaises(ValueError): self.channel.resolve(reply)

    def test_stop_releases_waiter_and_rejects_late_result(self):
        future = self.pool.submit(self.channel.call, 'pm_list_tasks', {})
        self.assertTrue(self.event.wait(1)); reply = self.reply()
        self.channel.cancel()
        with self.assertRaisesRegex(RuntimeError, 'cancelled'): future.result(1)
        with self.assertRaises(ValueError): self.channel.resolve(reply)

    def test_timeout_is_not_retried(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'): self.channel.call('pm_list_tasks', {})
        self.assertEqual(len(self.events), 1)
        with self.assertRaises(ValueError): self.channel.resolve(self.reply())

    def test_codex_foreign_turn_cannot_invoke_workspace(self):
        self.channel.set_active(('thread', 'turn'))
        for params in ({}, {'threadId':'thread','turnId':'old','tool':'pm_list_tasks','arguments':{}},
                       {'threadId':'thread','turnId':'turn','namespace':'bad','tool':'pm_list_tasks','arguments':{}}):
            self.assertFalse(self.channel.codex_call(params)['success'])
        self.assertEqual(self.events, [])

    def test_argument_catalog_blocks_unknown_extra_and_wrong_types(self):
        for name,args in [('execute',{}),('pm_list_tasks',{'command':'rm'}),('pm_ask_user',{'question':'x','options':'y'}),
                          ('pm_browser_action',{'browser_id':'b','snapshot_id':'s','element_id':'1','action':'eval','text':'x'})]:
            with self.assertRaises(ValueError): validate_arguments(name,args)
        self.assertEqual(len({x['name'] for x in TOOLS}),len(TOOLS))
        self.assertTrue(all(x['type']=='function' and x['inputSchema']['additionalProperties'] is False for x in TOOLS))

    def test_tool_error_is_explicit_and_payload_is_not_logged(self):
        future=self.pool.submit(self.channel.call,'pm_list_tasks',{})
        self.assertTrue(self.event.wait(1))
        self.channel.resolve({**self.reply(), 'success':False, 'error':'The tab closed.'})
        with self.assertRaisesRegex(RuntimeError,'tab closed'): future.result(1)
        self.assertNotIn('result',self.events[0])

    def test_stdio_reply_does_not_deadlock_behind_the_running_turn(self):
        from proto_mind.native_bridge import serve
        received = queue.Queue()
        class Destination:
            def write(self, value): received.put(json.loads(value))
            def flush(self): pass
        class Backend:
            workspace_tools = None
            def dispatch(self, method, params, emit, request_id):
                self.workspace_tools = WorkspaceTools(request_id,'conversation',emit,timeout=2)
                return self.workspace_tools.call('pm_list_tasks',{})
            def disconnect(self):
                if self.workspace_tools: self.workspace_tools.cancel()
            def close(self): pass
        reader, writer = os.pipe()
        with os.fdopen(reader) as source, os.fdopen(writer,'w',buffering=1) as input_pipe:
            thread = threading.Thread(target=serve,args=(Backend(),source,Destination()),daemon=True)
            thread.start()
            input_pipe.write(json.dumps({'id':'active','method':'process','params':{}})+'\n')
            event = received.get(timeout=3)
            input_pipe.write(json.dumps({'id':'reply','method':'workspace_tool_result','params':dict(
                request_id='active',call_id=event['call_id'],success=True,result={'tasks':['exact']},error='')})+'\n')
            replies = [received.get(timeout=3), received.get(timeout=3)]
            completed = next(reply for reply in replies if reply['id']=='active')
            self.assertEqual(completed['result'], {'tasks':['exact']})
            input_pipe.close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
