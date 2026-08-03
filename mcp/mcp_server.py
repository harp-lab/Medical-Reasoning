"""kg2 — a local stdio MCP server exposing RTX-KG2 query capabilities.

Claude Code orchestrates: it resolves entities with these tools, writes the Slog
Datalog itself, runs it, and names the results. The server holds no LLM key and does no
reasoning. Query conventions live in instructions/kg2.md, loaded below and surfaced to
the client as the server's instructions.

Queries run against a long-lived Slog session (slog/slog_server.rkt) that keeps the KG
resident, so a query costs a compile rather than a reload. Start that server separately
with slog/kg2-server.sh.
"""
import json
import os
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import kg2_core as core
import slog_client as slog
import slog_ir as ir

INSTRUCTIONS = (Path(__file__).resolve().parent / "instructions" / "kg2.md").read_text()
MAX_ROWS = 500  # cap query rows so a large result set can't flood the context

# Cache misses are logged with their canonical skeleton; if the same skeleton keeps
# recurring with different constants, that is the evidence for building subsumption
# matching (see docs/STATUS.md).
MISS_LOG = Path(os.environ.get(
    "KG2_MISS_LOG",
    Path(__file__).resolve().parent.parent / "docs" / "cache-misses.jsonl"))

mcp = FastMCP("kg2", instructions=INSTRUCTIONS)


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


@mcp.tool()
def list_predicates() -> list[str]:
    """Valid RTX-KG2 biolink predicates (e.g. 'biolink:treats'), most-frequent first."""
    return core.load_predicates()


@mcp.tool()
def resolve_entity(term: str, limit: int = 10, biolink_type: str = "") -> list[dict]:
    """Resolve an entity mention to candidate concepts; ask the user if the senses are ambiguous."""
    return core.resolve_term(term, limit=limit, biolink_type=biolink_type or None)


@mcp.tool()
def search_nodes(term: str, limit: int = 25) -> list[dict]:
    """Fallback search: case-insensitive substring over node names/synonyms, for terms NameRes misses."""
    return core.search_nodes(term, limit=limit)


@mcp.tool()
def expand_entity(curies: list[str]) -> dict:
    """Expand chosen CURIEs to the exact KG2 id set to match; returns {kg2_ids, per_curie}."""
    combined, per_curie = [], []
    for cid in curies:
        kept, clique = core.expand_to_kg2(cid)
        per_curie.append({"curie": cid, "clique_n": len(clique), "kept_n": len(kept), "kg2_ids": kept})
        combined.extend(kept)
    return {"kg2_ids": list(dict.fromkeys(combined)), "per_curie": per_curie}


@mcp.tool()
def session_status() -> dict:
    """Whether the Slog session is loaded, and what it is holding.

    A cold session loads on the first query: several minutes and tens of GB. Call this
    first if you want to know whether the next query will be fast or slow.
    """
    try:
        st = slog.status()
    except slog.SlogUnavailable as e:
        return {"available": False, "hint": str(e),
                "available_ram_gb": slog.available_ram_gb()}
    return {"available": True, "loaded": st.get("loaded"), "db": st.get("db"),
            "load_s": st.get("load_s"), "uptime_s": st.get("uptime_s"),
            "suspect": st.get("suspect"), "slogd_rss_gb": slog.slogd_rss_gb(),
            "available_ram_gb": slog.available_ram_gb()}


@mcp.tool()
def kg_schema() -> list[dict]:
    """Every relation live in the session, with its arity.

    Includes the base KG relations, the convenience views, and anything earlier queries
    derived — a later query can join against those instead of recomputing them. Loads
    the KG if the session is cold.
    """
    return [{"relation": n, "arity": a} for n, a in slog.schema()]


def _log_miss(program, h):
    """Record the canonical skeleton of a cache miss, for the subsumption decision."""
    try:
        MISS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with MISS_LOG.open("a") as f:
            f.write(json.dumps({"t": round(time.time()), "hash": h,
                                "canonical": ir.canonicalize(program)}) + "\n")
    except Exception:
        pass  # logging must never break a query


@mcp.tool()
def run_slog(program: str, limit: int = MAX_ROWS) -> dict:
    """Run a Slog program over RTX-KG2 (see the server instructions for conventions).

    The answer relation must be declared and named `result`; it is renamed internally to
    a content-addressed name, so two questions never collide and asking the same question
    twice reuses the first answer instead of recomputing it.

    Validates against the live schema before compiling, so mistakes come back in
    milliseconds rather than after a clang build. Returns {n_rows, returned, truncated,
    rows, cached, elapsed_s, relation}.
    """
    try:
        live = slog.schema()
    except slog.SlogUnavailable as e:
        return {"error": str(e), "rows": []}

    problems = ir.validate(program, live, predicates=core.load_predicates())
    if problems:
        return {"error": "program rejected before compiling", "problems": problems,
                "rows": [], "hint": "fix these and resubmit; nothing was run"}

    try:
        h = ir.canonical_hash(program)
    except ValueError as e:
        return {"error": f"could not canonicalize: {e}", "rows": []}
    rel = f"q_{h}"
    program_out = ir.rewrite_output(program, rel)

    live_names = {n for n, _ in live}
    cached = rel in live_names
    elapsed = 0.0
    if not cached:
        _log_miss(program, h)
        try:
            res = slog.run(program_out)
            elapsed = res.get("elapsed_s", 0.0)
        except slog.SlogError as e:
            return {"error": str(e), "rows": [],
                    "hint": "the session rejected or failed the program; "
                            "check session_status for a memory problem"}

    try:
        d = slog.dump(rel, limit=min(limit, MAX_ROWS))
    except slog.SlogError as e:
        return {"error": f"ran but could not read {rel}: {e}", "rows": []}

    return {"n_rows": d["n_rows"], "returned": d["returned"], "truncated": d["truncated"],
            "rows": d["rows"], "cached": cached, "elapsed_s": elapsed, "relation": rel}


@mcp.tool()
def name_curies(curies: list[str]) -> list[dict]:
    """Map result CURIEs to readable rows [{id, name, category}]."""
    return core.name_curies(curies)


if __name__ == "__main__":
    mcp.run()
