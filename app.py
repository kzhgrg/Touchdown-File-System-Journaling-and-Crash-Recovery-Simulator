"""Local HTTP server. Python standard library only; no pip install required."""
import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from engine import FileSystem

ROOT = Path(__file__).resolve().parent


def make_server(data_dir, port):
    fs = FileSystem(data_dir)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, payload, mime='application/json; charset=utf-8'):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if not isinstance(payload, bytes) else payload
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/api/state', '/api/export'):
                with lock:
                    self.send(200, fs.state())
                return
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
            if path not in assets:
                self.send(404, {'error': 'Not found'})
                return
            name, mime = assets[path]
            self.send(200, (ROOT / 'static' / name).read_bytes(), mime)

        def do_POST(self):
            # Browser requests must originate from this local server.
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                self.send(403, {'error': 'Unexpected request origin'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16384:
                    raise ValueError('Request size must be between 1 and 16384 bytes.')
                obj = json.loads(self.rfile.read(size))
                if not isinstance(obj, dict):
                    raise ValueError('Expected a JSON object.')
                action = urlsplit(self.path).path
                with lock:
                    if action == '/api/start':
                        fs.start(obj.get('op'), obj.get('name'), obj.get('content', ''))
                    elif action == '/api/step':
                        fs.step()
                    elif action == '/api/run':
                        fs.run()
                    elif action == '/api/crash':
                        fs.crash()
                    elif action == '/api/recover':
                        fs.recover()
                    elif action == '/api/mode':
                        fs.set_mode(obj.get('enabled'))
                    elif action == '/api/reset':
                        if obj.get('confirm') != 'RESET':
                            raise ValueError('Reset confirmation required.')
                        fs.reset()
                    else:
                        self.send(404, {'error': 'Unknown action'})
                        return
                    self.send(200, fs.state())
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {'error': str(exc)})
            except OSError:
                self.send(500, {'error': 'Could not save simulator data. Check folder permissions and free space.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Touchdown: file system crash recovery simulator')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(args.data_dir, args.port)
    except OSError as exc:
        parser.exit(1, f'Could not start: {exc}\nTry a different port: python app.py --port 8001\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'\nTouchdown is ready: {url}\nPress Ctrl+C to stop. Your virtual disk is saved automatically.\n')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nTouchdown stopped.')
    finally:
        server.server_close()
