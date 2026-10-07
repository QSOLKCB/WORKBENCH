"""Local-only browser transport over exactly the same Runtime as CLI/TUI."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .model import json_loads

STATIC = Path(__file__).with_name("static")


def make_server(runtime, port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid recording authorization material or local prompts.

        def send(self, status, body, content_type="application/json"):
            if content_type == "application/json":
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                self.send(403, {"error": "Unexpected Host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + host:
                self.send(403, {"error": "Unexpected Origin"})
                return False
            if self.path.startswith("/api/") and not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token):
                self.send(401, {"error": "Open the URL printed by the workbench server"})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/manifest":
                    self.send(200, runtime.manifest())
                elif path == "/api/runs":
                    self.send(200, runtime.history())
                elif path.startswith("/api/runs/"):
                    self.send(200, runtime.get(path.removeprefix("/api/runs/")))
                elif path in ("/", "/app.js", "/style.css"):
                    name, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                                  "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                    self.send(200, (STATIC / name).read_bytes(), mime)
                else:
                    self.send(404, {"error": "Not found"})
            except (ValueError, OSError, KeyError) as error:
                self.send(404, {"error": str(error)})

        def do_POST(self):
            if not self.allowed():
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Content-Type must be application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 65536 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Request must contain 1–65536 bytes with Content-Length")
                self.connection.settimeout(5)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request")
                body = json_loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("Body must be an object")
                if self.path == "/api/run":
                    result = runtime.start(body["action"], body.get("parameters", {}), body.get("schema_sha256"))
                    self.send(202, result)
                elif self.path == "/api/cancel":
                    self.send(200, runtime.cancel(body["id"]))
                elif self.path == "/api/refresh":
                    self.send(200, runtime.refresh())
                else:
                    self.send(404, {"error": "Not found"})
            except (ValueError, TypeError, KeyError, OSError) as error:
                self.send(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.workbench_token = token
    return server


def serve(runtime, port):
    server = make_server(runtime, port)
    print(f"Open http://127.0.0.1:{server.server_port}/#token={server.workbench_token}", flush=True)
    print("Local workbench. Ctrl+C stops the server and cancels its active jobs.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
