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


def _dump_rows(rel):
    """The relation's rows, or None if it does not exist yet.  $stat_work is
    only created once some rule has published work, so its absence is normal."""
    try:
        return slog.dump(rel, limit=100000)["rows"]
    except Exception:
        return None


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
        # $stat_work(loc, tag, ticks, driver_rows) publishes a fresh row per
        # stratum fixpoint carrying the DELTA since the last publication, so the
        # per-run delta is the set of rows that were not there before.
        return {"max_pos": max_pos, "fires": fires,
                "work": {tuple(r) for r in (_dump_rows("$stat_work") or [])}}
    except Exception as e:
        log.warning(f"could not read stat snapshot: {e!r}")
        return None


WORK_TOP_N = 6


def work_delta(before):
    """Where this run's join work went: $stat_work(loc, tag, ticks, driver_rows).

    This -- not $stat_fires -- is the blowup observable: a probe that scans
    millions of rows and never fires is invisible to the fire counters and
    visible here.  The tag keeps the `#N` suffix that $stat_fires strips, so a
    dynamic tail arm is attributed exactly; closed-rule whole-order arms carry
    driver-named `all:<rel>` tags instead, which say which driver ran just as
    plainly.

    Caveat worth knowing before reading a zero: only INTERPRETED rules (and
    native arm tasks) meter.  Under SLOG_OPT=0 the strata run natively, so a
    plain non-arm rule contributes nothing here -- 0 ticks means "nothing
    interpreted", not "no work"."""
    empty = {"work_ticks": None, "work_rows": None, "work_top": None}
    if not before:
        return empty
    rows = _dump_rows("$stat_work")
    if rows is None:
        return empty
    try:
        fresh = [r for r in rows if tuple(r) not in before["work"]]
        top = sorted(fresh, key=lambda r: -int(r[2]))[:WORK_TOP_N]
        return {"work_ticks": sum(int(r[2]) for r in fresh),
                "work_rows": sum(int(r[3]) for r in fresh),
                "work_top": ";".join(f"{r[0]}|{r[1]}={r[2]}" for r in top)[:900]
                            or None}
    except Exception as e:
        log.warning(f"could not read work delta: {e!r}")
        return empty


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
        # One .plan per compiled stratum.  Counting .cpp instead double-counts:
        # a stratum emits <hash>.cpp AND <hash>.p1.cpp (and .p2.cpp ...), so a
        # single fresh stratum used to report as 2-3 "strata compiled".
        n_strata = sum(1 for p in fresh if p.endswith(".plan"))
        blocking_o2 = (os.environ.get("SLOG_OPT") == "2")
        # `action-<id>.so` plugins are built for every dump/drop and are not
        # stratum code; letting them into `waited` made compile_s report the
        # action build instead of the stratum's.
        o0 = [p for p in fresh if p.endswith(".O0.so")]
        o2 = [p for p in fresh
              if p.endswith(".so") and not p.endswith(".O0.so")
              and not os.path.basename(p).startswith("action-")]
        waited = o2 if (blocking_o2 or not o0) else o0
        if not waited:
            return n_strata, 0.0
        return n_strata, max(0.0,
                             max(os.path.getmtime(p) for p in waited) - t_start)
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
