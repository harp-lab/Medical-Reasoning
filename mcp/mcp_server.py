"""kg2 — a local stdio MCP server exposing RTX-KG2 query capabilities.

Claude Code orchestrates: it resolves entities with these tools, writes the Soufflé
Datalog itself, runs it, and names the results. The server holds no LLM key and does no
reasoning — it is a thin wrapper around kg2_core. Query conventions live in
instructions/kg2.md, loaded below and surfaced to the client as the server's instructions.
"""
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import kg2_core as core

INSTRUCTIONS = (Path(__file__).resolve().parent / "instructions" / "kg2.md").read_text()
MAX_ROWS = 500  # cap query rows so a large result set can't flood the context

mcp = FastMCP("kg2", instructions=INSTRUCTIONS)


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
    """Fallback search: match() regex over node names/synonyms, for terms NameRes misses."""
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
def run_datalog(program: str, name: str = "result", timeout_s: int = 600) -> dict:
    """Run a Soufflé program over RTX-KG2 (see the server instructions for conventions).

    The edge header is auto-prepended if omitted. Returns {n_rows, n_cols, returned,
    truncated, rows, wall_s, profile}; result rows are usually CURIEs — pass to name_curies.
    """
    if ".decl edge(" not in program:
        program = f"{core.EDGE_HEADER}\n\n{program}"
    res = core.run_souffle(program, out_name=name, timeout=timeout_s)
    shown = res["rows"][:MAX_ROWS]
    return {"n_rows": res["n_rows"], "n_cols": res["n_cols"], "returned": len(shown),
            "truncated": res["n_rows"] > len(shown), "rows": shown,
            "wall_s": res["wall_s"], "profile": res["profile"]}


@mcp.tool()
def name_curies(curies: list[str]) -> list[dict]:
    """Map result CURIEs to readable rows [{id, name, category}]."""
    return core.name_curies(curies)


if __name__ == "__main__":
    mcp.run()
