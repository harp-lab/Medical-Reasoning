"""Per-run performance metrics for the KG2 MCP server.

Kept out of mr_logging because it needs slog_client, which imports mr_logging.

Everything here is diagnostics.  Every function returns None / empty rather
than raising, so a broken measurement can never take a query down with it.

The cost model below was measured on this deployment (2026-08):

  total ~= 11s compile (only when the program text changes)
         + ~13s per derived relation

Evidence: a program deriving one relation and doing exactly ONE rule firing
still took ~13s and burned ~95 CPU-seconds, while deriving 2/3/4 relations
cost 27s/40s/65s.  Data volume was free -- a rule over biolink:affects
(4.7M edges) cost the same as one over a 12K-edge predicate.  The same
programs against a tiny database showed no per-stratum cost at all.
"""

import glob
import os
import re
import time

import slog_client as slog
from mr_logging import get_logger

log = get_logger("stats")

# Measured constants for the prediction; see the module docstring.
#
# COMPILE_S is the eager -O0 build the query blocks on under the default
# SLOG_OPT=tiered -- measured ~9.3s for one stratum, and roughly flat as
# strata are added because their modules compile in parallel.  The detached
# -O2 build that follows does not block the run.
COMPILE_S = 9.0
PER_STRATUM_S = 13.0

SLOG_ROOT = os.environ.get(
    "SLOG_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "slog"))
BUILD_DIR = os.environ.get("SLOG_BUILD_DIR", os.path.join(SLOG_ROOT, "build"))

_TABLE_RE = re.compile(r"^\s*table\s*\(\s*([A-Za-z_][\w-]*)", re.M)
_RULE_HEAD_RE = re.compile(r"^\s*rule\s*\(\s*([A-Za-z_][\w-]*)", re.M)


# --------------------------------------------------------------------------
# The program itself


def parse_program(text):
    """(n_tables_declared, n_derived_rels) for a Slog program.

    A derived relation is one that appears as a rule head: those are the
    stages the engine has to finish and store, and each one costs ~13s.
    Available even when compilation is cached, unlike the build-dir counts.
    """
    try:
        tables = _TABLE_RE.findall(text)
        heads = _RULE_HEAD_RE.findall(text)
        return len(tables), len(set(heads))
    except Exception as e:
        log.warning(f"could not parse program: {e!r}")
        return None, None


def predict(n_derived_rels, compiled):
    """Expected wall seconds for a program of this shape."""
    if n_derived_rels is None:
        return None
    return (COMPILE_S if compiled else 0.0) + PER_STRATUM_S * n_derived_rels


# --------------------------------------------------------------------------
# The daemon's own numbers
#
# $stat_fixpoint rows are (push position, stratum hash, iterations, microsec)
# published at each stratum fixpoint; $stat_fires is (rule location, variant,
# count) of rule instantiations.  Both accumulate for the life of the session,
# so a single run's contribution is a delta.  Positions increase monotonically,
# which is what makes the fixpoint delta cheap and exact -- and unlike the
# build directory, this still reports correctly when compilation was cached.


def stat_snapshot():
    """State to diff against after a run; None if stats are unavailable."""
    try:
        fx = slog.dump("$stat_fixpoint", limit=100000)
        fr = slog.dump("$stat_fires", limit=100000)
    except Exception:
        return None  # no session yet, or stats disabled via SLOG_NO_STATS
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
    """What the daemon says this run cost: strata, fixpoint ms, iterations, fires."""
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


# --------------------------------------------------------------------------
# Compile vs execute, from the build directory
#
# Slog names build artifacts by content hash, so an unchanged program emits no
# new files -- which is exactly how a compile-cache hit is detected.


def build_snapshot():
    try:
        return {os.path.basename(p) for p in glob.glob(os.path.join(BUILD_DIR, "*"))}
    except Exception:
        return None


def build_delta(before, t_start):
    """(n_strata_compiled, compile_s): how many C++ modules were built, and how long.

    Only the compile the query actually WAITED on counts.  Under the default
    SLOG_OPT=tiered, that is the eager -O0 build (`<hash>.O0.so`); the plain
    `<hash>.so` is a detached -O2 build that lands in the background and
    hot-swaps in, so charging its link time to the query overstates compile and
    understates execution.  SLOG_OPT=2 is the mode that blocks for -O2.
    """
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
            return n_cpp, 0.0  # nothing linked => compile cache hit
        # Linking finishes last, so the newest artifact marks the end of the
        # compile the run was blocked on.
        return n_cpp, max(0.0, max(os.path.getmtime(p) for p in waited) - t_start)
    except Exception as e:
        log.warning(f"could not read build delta: {e!r}")
        return None, None


# --------------------------------------------------------------------------
# Machine state


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
    """(slogd_rss_gb, mem_avail_gb) -- how much memory the session holds."""
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
