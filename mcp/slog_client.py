import json
import os
import socket
import threading
import time

from mr_logging import fmt_dur, get_logger

HOST = os.environ.get("SLOG_SERVER_HOST", "127.0.0.1")
PORT = int(os.environ.get("SLOG_SERVER_PORT", "8642"))
TIMEOUT_S = int(os.environ.get("SLOG_CLIENT_TIMEOUT", "3600"))

log = get_logger("slog")

_lock = threading.Lock()


class SlogUnavailable(RuntimeError):
    pass


class SlogError(RuntimeError):
    pass


def request(op):
    payload = (json.dumps(op) + "\n").encode()
    kind = op.get("op", "?")
    log.info(f"  -> slog {kind}: {json.dumps(op)}")

    t_wait = time.perf_counter()
    with _lock:
        waited = time.perf_counter() - t_wait
        if waited > 0.5:
            log.warning(f"  .. waited {fmt_dur(waited)} for the slog client lock "
                        f"(another request was in flight)")
        t0 = time.perf_counter()
        try:
            conn = socket.create_connection((HOST, PORT), timeout=TIMEOUT_S)
        except OSError as e:
            log.error(f"  x cannot reach slog server at {HOST}:{PORT} -- {e}")
            raise SlogUnavailable(
                f"no Slog session server on {HOST}:{PORT} ({e}). "
                f"Start it with slog/kg2-server.sh."
            ) from e
        try:
            conn.sendall(payload)
            log.debug(f"  .. sent {len(payload)} bytes, waiting for the reply "
                      f"(timeout {TIMEOUT_S}s)")
            line = conn.makefile().readline()
        finally:
            conn.close()
    elapsed = time.perf_counter() - t0

    if not line:
        log.error(f"  x slog {kind} closed the connection after {fmt_dur(elapsed)}")
        raise SlogError("session server closed the connection without responding")

    resp = json.loads(line)
    if not resp.get("ok"):
        log.error(f"  x slog {kind} failed after {fmt_dur(elapsed)}: "
                  f"{resp.get('error', 'unknown error')}")
        raise SlogError(resp.get("error", "unknown error"))

    log.info(f"  <- slog {kind} ok in {fmt_dur(elapsed)} "
             f"({len(line)} bytes of response)")
    if elapsed > 60:
        log.warning(f"  !! slog {kind} took {fmt_dur(elapsed)}")
    return resp


def run_file(path):
    return request({"op": "run", "path": str(path)})


def dump(rel, limit=500):
    return request({"op": "dump", "rel": rel, "limit": limit})


def drop(rel):
    return request({"op": "drop", "rel": rel})
