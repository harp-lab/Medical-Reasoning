"""Net-effect mode: weigh a shape's routes in BOTH directions, in Slog.

With the flag off, a query locks its direction (`(= prod -1)`) and `result` holds
whatever matched.  With it on, the query instead fills `evidence(drug, effect,
route, strength)` with every route in either direction, and slog/net.slog -- a
fixed layer appended here -- decides per drug whether the net evidence favours the
goal.  The query never states a direction; the goal is one literal substituted in.

Shared by mcp_server.run_slog and `orion execute --net`.
"""
import re
from pathlib import Path

SLOG_DIR = Path(__file__).resolve().parent.parent / "slog"
LAYER_FILE = SLOG_DIR / "net.slog"
# What actually runs: query.slog + the layer.  Rewritten every net run, so the
# archived copy in logs/ is the record (slog/generated/ is gitignored).
ASSEMBLED_FILE = SLOG_DIR / "generated" / "query.net.slog"

# Every relation the layer writes, `evidence` included.  A session segment that
# writes an existing relation ADDS to it (slog docs/user/api.md, "Run program
# segments"), so all of these are dropped before a net run -- dropping `result`
# alone would let one question's routes leak into the next one's verdicts.
NET_RELS = ("evidence", "net_dir", "net_paths", "net_best", "result")

# Per-drug rows, so this is the number of candidates, not of routes.  Fetched
# whole so the ranking below sees every candidate before the 50-row cap applies.
DUMP_MAX = 20000

COLUMNS = ("drug", "verdict", "basis", "routes_for", "routes_against",
           "best_for", "best_against")


class NetQueryError(ValueError):
    pass


def _code(program):
    """The program with `;;` comments removed, for the shape checks below."""
    return "\n".join(line.split(";;", 1)[0] for line in program.splitlines())


def assemble(program, goal=-1):
    """query.slog + the layer, with the goal filled in.  Raises NetQueryError on a
    query that cannot work in net mode, before anything is sent to the server."""
    if goal not in (-1, 1):
        raise NetQueryError(f"goal must be -1 (lower the target) or 1 (raise it), "
                            f"not {goal!r}")
    code = _code(program)
    if not re.search(r"(rule|-->)\s*\(\s*evidence\b", code):
        raise NetQueryError(
            "the query must write `evidence(drug, effect, route, strength)` -- this "
            "one never does.  See 'Net-effect mode' in mcp/instructions/kg2.md")
    if re.search(r"(table|rule|-->)\s*\(\s*result\b", code):
        raise NetQueryError(
            "`result` belongs to slog/net.slog -- the query must not declare or "
            "write it.  Write `evidence` instead")
    layer = (LAYER_FILE.read_text()
             .replace("@GOAL@", str(goal))
             .replace("@OPPOSITE@", str(-goal)))
    return program.rstrip("\n") + "\n\n" + layer


def write_assembled(text):
    ASSEMBLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    ASSEMBLED_FILE.write_text(text)
    return ASSEMBLED_FILE


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def rank(rows):
    """Good verdicts first; within each, the widest strength margin, then the
    widest route margin.  Ordering only -- every verdict was decided in Slog."""
    def key(r):
        nf, na, bf, ba = (_int(x) for x in r[3:7])
        return (r[1] != "good", -(bf - ba), -(nf - na), -nf, r[0])
    return sorted(rows, key=key)


def tally(rows):
    """{verdict: n} and {basis: n} over every candidate."""
    verdicts, bases = {}, {}
    for r in rows:
        verdicts[r[1]] = verdicts.get(r[1], 0) + 1
        bases[r[2]] = bases.get(r[2], 0) + 1
    return {"verdicts": verdicts, "bases": bases}
