from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PID_FILE = Path(os.environ.get('OLLAMA_PID_FILE', '/Volumes/Personal/here-i-am/run/ollama.pid'))
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
app = FastAPI(title='Ollama Control Bridge')
LOCAL_BRIDGE_TOKEN = os.environ.get('LOCAL_BRIDGE_TOKEN', '')


@app.middleware('http')
async def protect_mutations(request: Request, call_next):
    if request.method != 'GET' and (
        not LOCAL_BRIDGE_TOKEN
        or request.headers.get('X-Here-I-Am-Local') != LOCAL_BRIDGE_TOKEN
    ):
        return JSONResponse(status_code=403, content={'detail': 'Local bridge authorization is required'})
    return await call_next(request)


def is_port_open(host: str = '127.0.0.1', port: int = 11434) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def api_reachable() -> bool:
    try:
        resp = requests.get(f'{OLLAMA_URL}/api/tags', timeout=2)
        return resp.ok
    except Exception:
        return False


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def is_launcher_ollama(pid: int) -> bool:
    completed = subprocess.run(
        ['ps', '-p', str(pid), '-o', 'command='],
        capture_output=True,
        text=True,
        check=False,
        timeout=3,
    )
    command = completed.stdout.strip()
    return completed.returncode == 0 and 'ollama serve' in command


@app.post('/auth/check')
def auth_check():
    return {'status': 'ok'}


@app.get('/status')
@app.get('/ollama/status', include_in_schema=False)
def status():
    pid = read_pid()
    return {
        'status': 'running' if api_reachable() else 'stopped',
        'pid': pid,
        'detail': 'Ollama API reachable' if api_reachable() else 'Ollama API not reachable',
    }


@app.post('/start')
@app.post('/ollama/start', include_in_schema=False)
def start():
    if api_reachable():
        return {'status': 'running', 'detail': 'Ollama already running', 'pid': read_pid()}
    process = subprocess.Popen(
        ['ollama', 'serve'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    write_pid(process.pid)
    for _ in range(20):
        time.sleep(1)
        if api_reachable():
            return {'status': 'running', 'detail': 'Ollama started', 'pid': process.pid}
    return JSONResponse(status_code=500, content={'status': 'error', 'detail': 'Ollama did not become ready'})


@app.post('/stop')
@app.post('/ollama/stop', include_in_schema=False)
def stop():
    pid = read_pid()
    if pid and is_launcher_ollama(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    elif pid:
        return JSONResponse(
            status_code=409,
            content={'status': 'refused', 'detail': 'The saved PID does not belong to launcher-owned Ollama'},
        )
    else:
        return {'status': 'stopped', 'detail': 'No launcher-owned Ollama process is recorded'}
    time.sleep(1)
    return {'status': 'stopped', 'detail': 'Stop signal sent to Ollama'}
