#!/usr/bin/env python3
"""Serve audit.html on localhost and proxy AI calls to a local Ollama server.

Everything runs offline (no internet, no API keys). Audit rules run in the
browser; "Ask AI" and "second opinion" use a small model served by Ollama
(e.g. qwen2.5:3b). This script only exists to avoid browser CORS errors.

Usage:
    python local_server.py                      # http://127.0.0.1:8000/audit.html
    python local_server.py --port 8123

Point at a different Ollama host with the environment variable:
    OLLAMA_URL=http://127.0.0.1:11434   (default)
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

OLLAMA_TIMEOUT = 300


def proxy(method, rel_path, body=None):
    """Forward a request to Ollama. Returns (status_code, body_bytes, content_type)."""
    url = OLLAMA + rel_path
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        payload = json.loads(body)
        if rel_path == "/api/chat":
            payload["stream"] = False
            opts = dict(payload.pop("options", None) or {})
            opts.setdefault("temperature", 0.2)
            opts.setdefault("num_predict", 700)
            payload["options"] = opts
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return resp.status, resp.read(), resp.headers.get_content_type() or "application/json"
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers.get_content_type() or "application/json"
    except Exception as err:  # noqa: BLE001 - connection refused / timeouts
        msg = json.dumps({"error": "Ollama is not reachable at %s (%s). "
                                  "Start it (ollama serve) and pull a model first."
                           % (OLLAMA, err)}).encode("utf-8")
        return 503, msg, "application/json"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):  # keep the console quiet
        pass

    def end_headers(self):
        # never let the browser cache the page or proxy responses
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _respond(self, status, data, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._respond(status, json.dumps(obj).encode("utf-8"), "application/json")

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": "bad JSON body"})
            return None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/index.htm"):
            self.path = "/audit.html"
            super().do_GET()
        elif path == "/local/client.json":
            self._json(200, {"ollama_url": OLLAMA, "proxied": True})
        elif path == "/local/tags":
            status, body, ctype = proxy("GET", "/api/tags")
            self._respond(status, body, ctype)
        else:
            super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/local/chat":
            payload = self._read_json()
            if payload is None:
                return
            if not payload.get("messages"):
                self._json(400, {"error": "'messages' array is required"})
                return
            status, body, ctype = proxy("POST", "/api/chat",
                                        json.dumps(payload).encode("utf-8"))
            self._respond(status, body, ctype)
        else:
            self._json(404, {"error": "not found"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Serve audit.html + proxy AI calls to a local Ollama server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    try:
        import webbrowser
        webbrowser.open("http://%s:%d/audit.html" % (args.host, args.port))
    except Exception:
        pass
    print("Data Quality Auditor  ->  http://%s:%d/audit.html" % (args.host, args.port))
    print("Ollama proxy          ->  %s  (set OLLAMA_URL to change)" % OLLAMA)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()