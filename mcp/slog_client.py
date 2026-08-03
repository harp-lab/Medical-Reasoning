"""Client for the long-lived Slog session server (slog/slog_server.rkt).

One resident slogd holds the KG, so every request serializes onto it: the lock
here keeps concurrent MCP tool calls from interleaving on one socket-per-request
protocol. Diagnostics go to stderr; stdout carries the MCP JSON-RPC stream.
"""
import json
import os
import socket
import subprocess
import sys
import threading

HOST = os.environ.get("SLOG_SERVER_HOST", "127.0.0.1")
PORT = int(os.environ.get("SLOG_SERVER_PORT", "8642"))
# A cold server has to load ~97 GB before it answers the first request.
TIMEOUT_S = int(os.environ.get("SLOG_CLIENT_TIMEOUT", "3600"))

_lock = threading.Lock()


class SlogUnavailable(RuntimeError):
    pass


class SlogError(RuntimeError):
    pass


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def request(op, timeout=None):
    """Send one request, return the parsed response dict. Raises on {ok:false}."""
    payload = (json.dumps(op) + "\n").encode()
    with _lock:
        try:
            conn = socket.create_connection((HOST, PORT), timeout=timeout or TIMEOUT_S)
        except OSError as e:
            raise SlogUnavailable(
                f"no Slog session server on {HOST}:{PORT} ({e}). "
                f"Start it with slog/kg2-server.sh; the first request then loads "
                f"the KG (~6 min, ~97 GB)."
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


def status():
    """Server state without triggering a load."""
    return request({"op": "status"}, timeout=30)


def schema():
    """[(name, arity)] of every live relation. Triggers the load if cold."""
    out = []
    for line in request({"op": "schema"}).get("relations", []):
        # "(schema-rel table edge 3)"
        parts = line.strip("()").split()
        if len(parts) >= 4:
            out.append((parts[2], int(parts[3])))
    return out


def run(program):
    return request({"op": "run", "program": program})


def dump(rel, limit=500):
    return request({"op": "dump", "rel": rel, "limit": limit})


def drop(rel):
    return request({"op": "drop", "rel": rel})


def slogd_rss_gb():
    """Resident size of the daemon, or None. Cheaper to read here than in Racket."""
    pid = status().get("slogd_pid")
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1048576, 1)
    except OSError:
        return None
    return None


def available_ram_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(int(line.split()[1]) / 1048576)
    except OSError:
        return None
    return None
