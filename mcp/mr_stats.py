import glob
import os
import re

import slog_client as slog
from mr_logging import get_logger

log = get_logger("stats")

COMPILE_S = 9.0
PER_STRATUM_S = 13.0

SLOG_ROOT = os.environ.get(
    "SLOG_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "slog"))
BUILD_DIR = os.environ.get("SLOG_BUILD_DIR", os.path.join(SLOG_ROOT, "build"))

_TABLE_RE = re.compile(r"^\s*table\s*\(\s*([A-Za-z_][\w-]*)", re.M)
_RULE_HEAD_RE = re.compile(r"^\s*rule\s*\(\s*([A-Za-z_][\w-]*)", re.M)


def parse_program(text):
    try:
        tables = _TABLE_RE.findall(text)
        heads = _RULE_HEAD_RE.findall(text)
        return len(tables), len(set(heads))
    except Exception as e:
        log.warning(f"could not parse program: {e!r}")
        return None, None


def predict(n_derived_rels, compiled):
    if n_derived_rels is None:
        return None
    return (COMPILE_S if compiled else 0.0) + PER_STRATUM_S * n_derived_rels


def stat_snapshot():
    try:
        fx = slog.dump("$stat_fixpoint", limit=100000)
        fr = slog.dump("$stat_fires", limit=100000)
    except Exception:
        return None
    try:
        max_pos = -1
        for r in fx["rows"]:
            max_pos = max(max_pos, int(r[0]))
        fires = {(r[0], r[1]): int(r[2]) for r in fr["rows"]}
        return {"max_pos": max_pos, "fires": fires}
    except Exception as e:
        log.warning(f"could not read stat snapshot: {e!r}")
        return None


def stat_delta(before):
    empty = {"n_strata_executed": None, "fixpoint_ms": None,
             "iterations": None, "rule_fires": None}
    if not before:
        return empty
    try:
        fx = slog.dump("$stat_fixpoint", limit=100000)
        fr = slog.dump("$stat_fires", limit=100000)
    except Exception:
        return empty
    try:
        strata = [r for r in fx["rows"] if int(r[0]) > before["max_pos"]]
        micros = sum(int(r[3]) for r in strata)
        iters = sum(int(r[2]) for r in strata)
        fires = 0
        for r in fr["rows"]:
            fires += int(r[2]) - before["fires"].get((r[0], r[1]), 0)
        return {"n_strata_executed": len(strata),
                "fixpoint_ms": round(micros / 1000.0, 1),
                "iterations": iters,
                "rule_fires": max(fires, 0)}
    except Exception as e:
        log.warning(f"could not read stat delta: {e!r}")
        return empty


def build_snapshot():
    try:
        return {os.path.basename(p) for p in glob.glob(os.path.join(BUILD_DIR, "*"))}
    except Exception:
        return None


def build_delta(before, t_start):
    if before is None:
        return None, None
    try:
        now = glob.glob(os.path.join(BUILD_DIR, "*"))
        fresh = [p for p in now if os.path.basename(p) not in before]
        n_cpp = sum(1 for p in fresh if p.endswith(".cpp"))
        blocking_o2 = (os.environ.get("SLOG_OPT") == "2")
        o0 = [p for p in fresh if p.endswith(".O0.so")]
        o2 = [p for p in fresh if p.endswith(".so") and not p.endswith(".O0.so")]
        waited = o2 if (blocking_o2 or not o0) else o0
        if not waited:
            return n_cpp, 0.0
        return n_cpp, max(0.0, max(os.path.getmtime(p) for p in waited) - t_start)
    except Exception as e:
        log.warning(f"could not read build delta: {e!r}")
        return None, None


def _slogd_pid():
    for p in glob.glob("/proc/[0-9]*/comm"):
        try:
            with open(p) as fh:
                if fh.read().strip() == "slogd":
                    return p.split("/")[2]
        except OSError:
            pass
    return None


def env_snapshot():
    rss = avail = None
    try:
        pid = _slogd_pid()
        if pid:
            with open(f"/proc/{pid}/statm") as fh:
                rss = round(int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                            / (1 << 30), 1)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    avail = round(int(line.split()[1]) / (1 << 20), 1)
                    break
    except Exception:
        pass
    return rss, avail
