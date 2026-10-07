import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, r"C:\Users\david\Documents\Hackathon")

class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _j(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/tags":
            self._j({"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:1b"}]})
        else:
            self._j({"error": "not found"})
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        body = json.loads(raw)
        self._j({"received": body,
                 "message": {"content": "fake reply ok"}})

fakesrv = ThreadingHTTPServer(("127.0.0.1", 11499), FakeOllama)
threading.Thread(target=fakesrv.serve_forever, daemon=True).start()

os.environ["OLLAMA_URL"] = "http://127.0.0.1:11499"
import local_server  # noqa: E402  (must import after env set)

proxysrv = ThreadingHTTPServer(("127.0.0.1", 18000), local_server.Handler)
threading.Thread(target=proxysrv.serve_forever, daemon=True).start()

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("http://127.0.0.1:18000" + path, data=data,
                               headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")

ok = fail = 0
def chk(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  ok  " + name)
    else: fail += 1; print("  FAIL " + name + "  => " + str(extra))

s, c = req("GET", "/audit.html")
chk("serves audit.html", s == 200 and "<!DOCTYPE html>" in c, s)
s, c = req("GET", "/")
chk("root redirects to audit.html", s == 200 and "<!DOCTYPE html>" in c, s)
s, c = req("GET", "/local/client.json")
chk("client config endpoint", s == 200 and "proxied" in c, (s, c[:60]))
s, c = req("GET", "/local/tags")
chk("proxies /api/tags", s == 200 and "qwen2.5:3b" in c, c[:90])
s, c = req("POST", "/local/chat", {
    "model": "qwen2.5:3b",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": True, "options": {"temperature": 0.9}})
chk("chat proxied 200", s == 200, s)
received = json.loads(c)["received"]
chk("stream forced to false", received["stream"] is False, received.get("stream"))
chk("options merged (temp kept, num_predict default)",
    received["options"].get("temperature") == 0.9 and
    received["options"].get("num_predict") == 700, received.get("options"))
s, c = req("POST", "/local/nope", {})
chk("unknown local POST -> 404", s == 404, s)

# proxy outage path: point the module at a dead Ollama
local_server.OLLAMA = "http://127.0.0.1:1"
st, body, ct = local_server.proxy("GET", "/api/tags")
chk("dead Ollama -> 503 JSON", st == 503 and '"error"' in body.decode(), (st, body[:80]))

print("\n%d ok, %d fail" % (ok, fail))
proxysrv.shutdown(); fakesrv.shutdown()
sys.exit(1 if fail else 0)