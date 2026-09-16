"""Serve only the synthetic brief on loopback; no dependencies or file listing."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    body = Path(__file__).with_name('brief.html').read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/brief.html'):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'Open in Proto-Mind: http://127.0.0.1:{server.server_port}/brief.html', flush=True)
        print('Ctrl+C stops this local demo server.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
