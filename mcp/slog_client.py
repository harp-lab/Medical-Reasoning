import json
import os
import socket
import threading

HOST = os.environ.get("SLOG_SERVER_HOST", "127.0.0.1")
PORT = int(os.environ.get("SLOG_SERVER_PORT", "8642"))
TIMEOUT_S = int(os.environ.get("SLOG_CLIENT_TIMEOUT", "3600"))

_lock = threading.Lock()


class SlogUnavailable(RuntimeError):
    pass


class SlogError(RuntimeError):
    pass


def request(op):
    payload = (json.dumps(op) + "\n").encode()
    with _lock:
        try:
            conn = socket.create_connection((HOST, PORT), timeout=TIMEOUT_S)
        except OSError as e:
            raise SlogUnavailable(
                f"no Slog session server on {HOST}:{PORT} ({e}). "
                f"Start it with slog/kg2-server.sh."
            ) from e
        try:
            conn.sendall(payload)
            line = conn.makefile().readline()
        finally:
            conn.close()
    if not line:
        raise SlogError("session server closed the connection without responding")
    resp = json.loads(line)
    if not resp.get("ok"):
        raise SlogError(resp.get("error", "unknown error"))
    return resp


def run_file(path):
    return request({"op": "run", "path": str(path)})


def dump(rel, limit=500):
    return request({"op": "dump", "rel": rel, "limit": limit})


def drop(rel):
    return request({"op": "drop", "rel": rel})
