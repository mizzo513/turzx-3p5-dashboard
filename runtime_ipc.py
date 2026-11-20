"""Localhost-only status/control channel. No polling JSON files are written.

The status endpoint is private to this computer, not an HTTP service.
"""
import json
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field

HOST = '127.0.0.1'
PORT = 48653

@dataclass
class IPCState:
    status: dict = field(default_factory=dict)
    stop_requested: threading.Event = field(default_factory=threading.Event)
    reconnect_requested: threading.Event = field(default_factory=threading.Event)
    ntp_sync_requested: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, **values):
        with self.lock:
            self.status = {'heartbeat': time.time(), **values}

    def read(self):
        with self.lock:
            return dict(self.status)

_current: IPCState | None = None

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(1.5)
        try:
            command = self.rfile.readline(64).strip().decode('ascii', errors='ignore').upper()
            if command == 'STATUS':
                response = self.server.state.read()
            elif command == 'STOP':
                self.server.state.stop_requested.set()
                response = {'ok': True}
            elif command == 'RECONNECT':
                self.server.state.reconnect_requested.set()
                response = {'ok': True}
            elif command == 'SYNC_NTP':
                # Signal the engine: the GUI never performs an independent
                # sync that would fail to update the LCD's actual clock.
                self.server.state.ntp_sync_requested.set()
                response = {'ok': True}
            else:
                response = {'error': 'unknown command'}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8')+b'\n')
        except (OSError, ValueError):
            pass

class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class StatusServer:
    def __init__(self):
        global _current
        self.state = IPCState()
        self.server = _Server((HOST, PORT), _Handler)
        self.server.state = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        _current = self.state

    def __enter__(self):
        self.thread.start()
        return self.state

    def __exit__(self, *exc):
        global _current
        self.server.shutdown()
        self.server.server_close()
        _current = None

def current_state():
    return _current

def send_command(command: str, timeout: float=0.4):
    with socket.create_connection((HOST, PORT), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(command.encode('ascii') + b'\n')
        chunks=bytearray()
        while len(chunks) < 8192:
            ch = s.recv(4096)
            if not ch: break
            chunks.extend(ch)
            if b'\n' in chunks: break
    return json.loads(bytes(chunks).split(b'\n')[0])

def get_runtime_status():
    try:
        state = send_command('STATUS')
        if time.time()-float(state.get('heartbeat',0)) > 4:
            return None
        return state
    except (OSError, ValueError, TypeError, IndexError):
        return None

def request_stop():
    try:
        return bool(send_command('STOP').get('ok'))
    except (OSError, ValueError, TypeError):
        return False


def request_reconnect():
    """Ask the running USB engine to close and re-open its port safely."""
    try:
        return bool(send_command('RECONNECT').get('ok'))
    except (OSError, ValueError, TypeError):
        return False


def request_ntp_sync():
    """Ask the active display engine to synchronize NTP immediately."""
    try:
        return bool(send_command('SYNC_NTP').get('ok'))
    except (OSError, ValueError, TypeError):
        return False
