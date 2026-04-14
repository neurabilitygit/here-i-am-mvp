#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socketserver
import subprocess
from http.server import BaseHTTPRequestHandler

PORT = int(os.getenv("OLLAMA_CONTROL_PORT", "11435"))
OLLAMA_MODELS = os.getenv("OLLAMA_MODELS", "/Volumes/Personal/here-i-am/models/ollama")


def is_ollama_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "ollama serve"], capture_output=True, text=True)
    return result.returncode == 0


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/start":
            if is_ollama_running():
                return self._send(200, {"ok": True, "detail": "Ollama already running", "status": "ready"})
            env = os.environ.copy()
            env["OLLAMA_MODELS"] = OLLAMA_MODELS
            subprocess.Popen(["ollama", "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self._send(200, {"ok": True, "detail": "Ollama start requested", "status": "starting"})
        if self.path == "/stop":
            subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True)
            return self._send(200, {"ok": True, "detail": "Ollama stop requested", "status": "stopped"})
        return self._send(404, {"ok": False, "detail": "Not found"})

    def do_GET(self):
        if self.path == "/status":
            return self._send(200, {"ok": True, "status": "ready" if is_ollama_running() else "stopped"})
        return self._send(404, {"ok": False, "detail": "Not found"})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
        print(f"Ollama control helper listening on 127.0.0.1:{PORT}")
        server.serve_forever()
