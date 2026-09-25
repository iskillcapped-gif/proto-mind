import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from proto_mind.native_mcp import MCPClient, perform, validate_connection, public_result


class MCPTests(unittest.TestCase):
    def server(self, outcome='normal', sse=False):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((value,self.headers.get('Authorization'),self.headers.get('MCP-Session-Id')))
                method=value['method']
                if method=='notifications/initialized': self.send_response(202); self.end_headers(); return
                if outcome=='disconnect' and method=='tools/call': self.close_connection=True; return
                result=({'protocolVersion':'2025-06-18','capabilities':{'tools':{}}} if method=='initialize' else
                        {'tools':[{'name':'echo','description':'fixture tool','inputSchema':{'type':'object'}}]} if method=='tools/list' else
                        {'content':[{'type':'text','text':'done'}]})
                reply={'jsonrpc':'2.0','id':value['id'] if outcome!='wrong_id' else 'another','result':result}
                self.send_response(200); self.send_header('MCP-Session-Id','fixture-session')
                self.send_header('Content-Type','text/event-stream' if sse else 'application/json'); self.end_headers()
                self.wfile.write((('data: '+json.dumps(reply)+'\n\n') if sse else json.dumps(reply)).encode())
            def log_message(self,*_): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        configuration={'transport':'http','endpoint':f'http://127.0.0.1:{server.server_port}/mcp','command':'','arguments':[],'secret':'synthetic-secret'}
        return configuration,calls

    def test_http_initialization_session_and_exact_call(self):
        configuration,calls=self.server()
        result=perform({'connection':configuration,'operation':'call','name':'echo','arguments':{'text':'fixture'}})
        self.assertEqual(result['result']['content'][0]['text'],'done')
        self.assertEqual([row[0]['method'] for row in calls],['initialize','notifications/initialized','tools/call'])
        self.assertEqual(calls[-1][2],'fixture-session')
        self.assertEqual(calls[-1][1],'Bearer synthetic-secret')
        self.assertNotIn('synthetic-secret',json.dumps(result))

    def test_sse_catalog(self):
        configuration,calls=self.server(sse=True)
        result=perform({'connection':configuration,'operation':'list'})
        self.assertEqual(result['tools'][0]['name'],'echo')

    def test_uncertain_action_is_not_replayed(self):
        configuration,calls=self.server('disconnect')
        with self.assertRaises(ValueError): perform({'connection':configuration,'operation':'call','name':'echo','arguments':{}})
        self.assertEqual(sum(row[0]['method']=='tools/call' for row in calls),1)

    def test_foreign_response_is_rejected_before_tools(self):
        configuration,calls=self.server('wrong_id')
        with self.assertRaisesRegex(ValueError,'identity'): perform({'connection':configuration,'operation':'list'})
        self.assertEqual(len(calls),1)

    def test_stdio_uses_argv_and_closes_only_owned_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            script=Path(temporary)/'fixture.py'
            script.write_text('''import json,sys
for line in sys.stdin:
 v=json.loads(line)
 if "id" not in v: continue
 result={"protocolVersion":"2025-06-18","capabilities":{"tools":{}}} if v["method"]=="initialize" else {"tools":[]}
 print(json.dumps({"jsonrpc":"2.0","id":v["id"],"result":result}),flush=True)
''')
            connection={'transport':'stdio','endpoint':'','command':sys.executable,'arguments':[str(script)],'secret':''}
            with MCPClient(connection,timeout=1) as client:
                process=client.process
                self.assertEqual(client.request('tools/list',{}),{'tools':[]})
            self.assertIsNotNone(process.poll())

    def test_remote_plaintext_and_embedded_credentials_are_rejected(self):
        for endpoint in ['http://remote.example/mcp','https://user:password@example.com/mcp','https://example.com/mcp?token=secret']:
            with self.assertRaises(ValueError): validate_connection({'transport':'http','endpoint':endpoint,'command':'','arguments':[],'secret':''})

    def test_echoed_credentials_never_leave_transport(self):
        value = {'content': [{'type':'text','text':'Bearer fixture-secret'}], 'nested': {'fixture-secret': 1}}
        sanitized = public_result(value, 'fixture-secret')
        self.assertNotIn('fixture-secret', json.dumps(sanitized))
        self.assertEqual(sanitized['nested']['[credential redacted]'], 1)

    def test_closed_client_cannot_start_another_request(self):
        configuration, calls = self.server()
        client = MCPClient(configuration, timeout=1)
        client.close()
        with self.assertRaisesRegex(ValueError, 'closed'): client.request('tools/list', {})
        self.assertEqual(calls, [])
