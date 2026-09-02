"""The join plan a query actually ran under.

Slog compiles each stratum to `build/<hash>.plan` -- a canonical s-expression
holding, per rule, the driver relation and the ordered tail of joins.  That file
IS the join order; nothing downstream reorders it (slog
docs/join-planning-assessment.md: "everything after only lowers the already-fixed
order").  Three channels give us the whole picture per run:

  1. `(fixpoint SCC "HASH" ITERS MS)` on the daemon's echo stream names the
     strata that ran, and HASH is the plan file's basename.
  2. `build/<hash>.plan` is the plan.  `(attrs (arm N GID))` on a rule-def marks
     it as one arm of a SLOG_MULTIPLAN choice group -- so an empty arm set here
     means multi-plan selection had nothing to choose between, whatever the flag
     said.
  3. `(arms (g GID ARM CONVERGED "LOC") ...)`, also on the echo stream, is the
     daemon's report of which arm its runtime selection settled on.

Which arm did the WORK is a fourth channel, the `$stat_work` counters -- that
one lives in mr_stats, because it is a runtime statistic like $stat_fires.
"""

import os
import re

from mr_logging import get_logger
from mr_stats import BUILD_DIR

log = get_logger("plan")

CSV_CELL_MAX = 900

# ---------------------------------------------------------------------------
# the .plan s-expression

_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+')


def _parse(text):
    """Nested lists.  Quoted strings lose their quotes and bare atoms stay raw
    text -- nothing here needs to tell "foo" from foo."""
    stack = [[]]
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            if len(stack) == 1:
                raise ValueError("unbalanced ')' in plan")
            top = stack.pop()
            stack[-1].append(top)
        elif t[0] == '"':
            stack[-1].append(t[1:-1])
        else:
            stack[-1].append(t)
    if len(stack) != 1:
        raise ValueError("unbalanced '(' in plan")
    return stack[0]


def _head(node, name):
    return isinstance(node, list) and bool(node) and node[0] == name


def _child(node, name):
    for c in (node or []):
        if _head(c, name):
            return c
    return None


def _children(node, name):
    return [c for c in (node or []) if _head(c, name)]


# ---------------------------------------------------------------------------
# rendering one rule's join order
#
# Op vocabulary from slog compiler/canonical-plan.rkt (canonicalize-crule).
# Only the relation-touching ops are join ORDER; let/letp/eq/neq/cmp/cjoin are
# per-row computation and would only make the line noisier.  `b=K` is the number
# of columns bound entering that step -- the selectivity signal the planner's
# score is built on, and the thing to look at when a plan is suspect.

_JOINS = {"join": "", "join-old": ":old", "join-new": ":new",
          "join-tomb": ":tomb", "join-lat": ":lat"}
_FILTERS = {"exists": "?", "absent": "!", "absent-old": "!old",
            "absent-new": "!new", "absent-ever": "!ever", "absent-lat": "!lat"}


def _rel(op, slots):
    r = op[1] if len(op) > 1 else None
    if _head(r, "rel"):
        return slots.get(r[1], f"rel{r[1]}")
    return str(r)


def _render_op(op, slots):
    if not isinstance(op, list) or not op:
        return None
    kind = op[0]
    if kind == "scan":                       # a delta/full scan has no bound prefix
        return f"{_rel(op, slots)}(scan)"
    if kind == "probe":                      # (probe rel ord K ...)
        return f"{_rel(op, slots)}(b={op[3]})"
    if kind in _JOINS:                       # (join rel ord K ...)
        return f"{_rel(op, slots)}(b={op[3]}){_JOINS[kind]}"
    if kind in _FILTERS:                     # semijoin filter / negation
        return f"{_FILTERS[kind]}{_rel(op, slots)}(b={op[3]})"
    if kind == "join3":                      # WCOJ leapfrog: (join3 cycle ARM ...)
        arms = [a for a in op[2:] if isinstance(a, list)]
        return "join3[" + " x ".join(_rel(a, slots) for a in arms) + "]"
    return None


def _render_rule(rd, slots, debug):
    steps = []
    drv = _child(rd, "driver")
    if drv and len(drv) > 1:
        steps.append(_render_op(drv[1], slots))
    for op in (_child(rd, "body") or [])[1:]:
        steps.append(_render_op(op, slots))
    steps = [s for s in steps if s]

    arm = gid = None
    a = _child(_child(rd, "attrs"), "arm")
    if a:
        arm, gid = int(a[1]), int(a[2])

    info = debug.get(_child(rd, "ord")[1], {})
    return {"arm": arm, "gid": gid,
            "variant": info.get("variant", ""),
            "source": info.get("source", ""),
            "order": " -> ".join(steps) or "(no relation steps)"}


def load_plan(stratum_hash):
    """The rules of build/<hash>.plan, or None if it is missing/unreadable."""
    path = os.path.join(BUILD_DIR, f"{stratum_hash}.plan")
    try:
        top = _parse(open(path, encoding="utf-8").read())[0]
    except Exception as e:
        log.warning(f"  !! could not read plan {path}: {e!r}")
        return None

    rules = []
    # A cohort holds the manifest's `(kernel (ord N) (key ...))` entries as well
    # as the real ones; only the latter carry an (exec ...).
    for k in _children(top, "kernel"):
        ex = _child(k, "exec")
        if not ex:
            continue
        slots = {s[1]: s[2] for s in _children(_child(k, "binding"), "slot")}
        debug = {}
        for r in _children(_child(k, "debug"), "rule"):
            debug[_child(r, "ord")[1]] = {
                "variant": (_child(r, "variant") or ["", ""])[1],
                "source": (_child(r, "source") or ["", ""])[1]}
        for rd in _children(_child(ex, "rules"), "rule-def"):
            rules.append(_render_rule(rd, slots, debug))
    # Every plan carries one `<internal>` error-arm rule per error struct
    # (div_by_zero, type_mismatch, ...).  They are the compiler's, identical in
    # every program, and would swamp the digest.
    internal = [r for r in rules if r["source"].startswith("<internal>")]
    rules = [r for r in rules if not r["source"].startswith("<internal>")]
    return {"hash": stratum_hash, "path": path, "rules": _by_source(rules),
            "n_internal": len(internal)}


def _by_source(rules):
    """Source order, so the listing reads like the query file.  Plan ordinals
    follow the canonical (hash) order, which is deterministic but arbitrary."""
    def key(r):
        f, _, ln = r["source"].rpartition(":")
        return (f, int(ln) if ln.isdigit() else 0)
    return sorted(rules, key=key)


# ---------------------------------------------------------------------------
# the daemon's echo stream

_FIXPOINT_RE = re.compile(r'^\(fixpoint (\d+) "([^"]*)" (\d+) ([0-9.]+)\)')
_TIER_RE = re.compile(r"^\(tier (\d+) (\S+) (\S+)\)")
_ARM_RE = re.compile(r'\(g (-?\d+) (-?\d+) (\d+) "([^"]*)"\)')


_STAMP_RE = re.compile(r"^\+(\d+) ")


def _timeline(events):
    """Milliseconds spent BEFORE each stamped daemon line.

    The daemon's own `(fixpoint ...)` ms covers the fixpoint loop only.  Stratum
    setup -- above all the whole-DB reload armed after every fixpoint, which
    re-stages every relation as delta and clears every index for the next
    stratum to re-intern -- happens between lines and is invisible to it.  These
    deltas are where an unaccounted gap actually went."""
    steps, prev = [], 0
    for line in (events or []):
        m = _STAMP_RE.match(line)
        if not m:
            continue
        at = int(m.group(1))
        steps.append({"at_ms": at, "delta_ms": at - prev,
                      "line": line[m.end():]})
        prev = at
    return steps


def _strip(events):
    return [_STAMP_RE.sub("", ln) for ln in (events or [])]


def parse_events(events):
    strata, arms, notes = [], [], []
    for line in _strip(events):
        m = _FIXPOINT_RE.match(line)
        if m:
            strata.append({"scc": int(m.group(1)), "hash": m.group(2),
                           "iterations": int(m.group(3)), "ms": float(m.group(4))})
            continue
        if line.startswith("(arms "):
            for gid, arm, conv, loc in _ARM_RE.findall(line):
                arms.append({"gid": int(gid), "arm": int(arm),
                             "converged": conv == "1", "loc": loc})
            continue
        m = _TIER_RE.match(line)
        if m:
            notes.append(f"stratum {m.group(1)} swapped to {m.group(3)}")
        elif line.startswith("(events-truncated"):
            notes.append(line)
    return {"strata": strata, "arms": arms, "notes": notes}


# ---------------------------------------------------------------------------
# the run's plans, as a CSV cell and as a readable block

def _digest(plans):
    """One compact cell.  Rules that share a join order collapse to `Nx <order>`
    -- a six-way disjunction over one shape is one plan, written six times."""
    parts = []
    for p in plans:
        groups = {}
        for r in p["rules"]:
            g = groups.setdefault(r["order"], {"n": 0, "arms": set()})
            g["n"] += 1
            if r["arm"] is not None:
                g["arms"].add(f"g{r['gid']}#{r['arm']}")
        body = " ; ".join(
            (f"{g['n']}x " if g["n"] > 1 else "") + order
            + (" [arm " + ",".join(sorted(g["arms"])) + "]" if g["arms"] else "")
            for order, g in groups.items())
        parts.append(f"{p['hash']}: {body}")
    cell = " | ".join(parts)
    return cell[:CSV_CELL_MAX - 3] + "..." if len(cell) > CSV_CELL_MAX else cell


def collect(resp):
    """Everything about the join plans of one run_slog, from the server reply.

    Returns {plans, arms, notes, env, csv} where `csv` is the summary.csv cells.
    """
    raw = resp.get("events") if isinstance(resp, dict) else None
    ev = parse_events(raw)
    env = (resp.get("env") or {}) if isinstance(resp, dict) else {}
    steps = _timeline(raw)

    plans = []
    for s in ev["strata"]:
        p = load_plan(s["hash"])
        if p:
            p.update(s)
            plans.append(p)

    n_arms = sum(1 for p in plans for r in p["rules"] if r["arm"] is not None)
    # `arm1` names nothing on its own.  The index is a position in that GROUP's
    # own candidate list (join-planning.rkt mints it with in-naturals 1), so arm
    # 1 of one group and arm 1 of another are different orders -- the only fixed
    # point is arm 0, which is always the compiler's own pick.  Carry the
    # relation each picked arm STARTS from, since for whole-order arms that is
    # exactly what the choice is between; otherwise the cell is unreadable
    # without cross-referencing the archived .plan listing by hand.
    starts = {(r["gid"], r["arm"]): r["order"].split("(")[0]
              for p in plans for r in p["rules"] if r["arm"] is not None}

    def _pick(a):
        start = starts.get((a["gid"], a["arm"]))
        return (f"{a['loc']}#g{a['gid']}=arm{a['arm']}"
                + (f"({start})" if start else "")
                + ("*" if a["converged"] else ""))

    picked = ";".join(_pick(a) for a in ev["arms"])
    # The heaviest inter-line stretches, biggest first: the phase breakdown of
    # the run, including the setup work no fixpoint ms accounts for.
    heavy = sorted(steps, key=lambda s: -s["delta_ms"])[:4]
    return {
        "plans": plans, "arms": ev["arms"], "notes": ev["notes"], "env": env,
        "steps": steps, "arm_starts": starts,
        "csv": {
            "phase_ms": ";".join(
                f"{s['line'].split(' ')[0].lstrip('(')}={s['delta_ms']}"
                for s in heavy if s["delta_ms"] > 0)[:CSV_CELL_MAX] or None,
            "plan_hashes": ";".join(p["hash"] for p in plans) or None,
            "join_plan": _digest(plans) or None,
            "n_arms": n_arms,
            "arms_picked": picked[:CSV_CELL_MAX] or None,
            # opt matters as much as the flag: SLOG_OPT=0 compiles to native -O0,
            # `interp` never invokes clang and is the only mode where $stat_work
            # sees anything.  Without it in the row you cannot tell which engine
            # produced a timing.
            "multiplan": (f"{env.get('multiplan') or 'off'}"
                          f"/{env.get('multiplan_index') or '-'}") if env else None,
            "slog_opt": (env.get("opt") or "tiered") if env else None,
        },
    }


def render(info):
    """The readable block: one line per rule, driver first, tail in order."""
    out = []
    for p in info["plans"]:
        out.append(f"stratum {p['scc']}  {p['hash']}  "
                   f"{p['iterations']} iteration(s), {p['ms']:.1f} ms  "
                   f"({p['path']}, +{p['n_internal']} internal error rules)")
        for r in p["rules"]:
            arm = f"   <- arm {r['gid']}#{r['arm']}" if r["arm"] is not None else ""
            out.append(f"    {r['source']:<20} {r['variant']:<20} "
                       f"{r['order']}{arm}")
    if info.get("steps"):
        out.append("  daemon timeline (ms between emitted lines -- setup work "
                   "lands here, not in the fixpoint ms):")
        for s in info["steps"]:
            # A `(paused ...)` line carries its CAUSE at the very end -- (budget
            # time), (budget memory), (boundary requested), a watch id.  That is
            # the whole diagnostic value of the line, so never clip it.
            keep = len(s["line"]) if s["line"].startswith("(paused") else 100
            out.append(f"    +{s['at_ms']:>8} ms  (+{s['delta_ms']:>8} ms)  "
                       f"{s['line'][:keep]}")
    if info["arms"]:
        out.append("  runtime arm selection (daemon report; arm 0 is the "
                   "compiler's own pick, so a non-zero arm means the runtime "
                   "measurement overrode it):")
        starts = info.get("arm_starts") or {}
        for a in info["arms"]:
            start = starts.get((a["gid"], a["arm"]))
            out.append(f"    {a['loc']} group {a['gid']} -> arm {a['arm']}"
                       f"{'  starting from ' + start if start else ''}"
                       f"{'  (converged)' if a['converged'] else ''}")
    for n in info["notes"]:
        out.append(f"  note: {n}")
    return "\n".join(out) if out else "(no plan recovered for this run)"
