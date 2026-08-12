import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import kg2_core as core
import slog_client as slog

INSTRUCTIONS = (Path(__file__).resolve().parent / "instructions" / "kg2.md").read_text()
MAX_ROWS = 500
OUTPUT_REL = "result"
QUERY_FILE = Path(os.environ.get(
    "KG2_QUERY_FILE",
    Path(__file__).resolve().parent.parent / "slog" / "query.slog"))

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
def expand_entity(curies: list[str]) -> dict:
    """Expand chosen CURIEs to the exact KG2 id set to match in a query."""
    combined = []
    for cid in curies:
        combined.extend(core.expand_to_kg2(cid))
    return {"kg2_ids": list(dict.fromkeys(combined))}


@mcp.tool()
def run_slog(limit: int = MAX_ROWS) -> dict:
    """Run the Slog program you have written to slog/query.slog.

    Write your program to that file first (with Write or Edit), then call this. It takes
    no program argument -- it always runs whatever is currently in the file, so the file
    is the record of what ran.

    The answer relation must be declared and named `result`. It is dropped before the
    program runs, so each query starts from an empty answer relation.

    Loading the KG takes several minutes on the first call of a session. Returns
    {n_rows, returned, truncated, rows, query_file}.
    """
    if not QUERY_FILE.exists():
        return {"error": f"{QUERY_FILE} does not exist -- write your Slog program there "
                         f"first, then call run_slog again", "rows": []}
    try:
        try:
            slog.drop(OUTPUT_REL)
        except slog.SlogError:
            pass
        slog.run_file(QUERY_FILE)
        d = slog.dump(OUTPUT_REL, limit=min(limit, MAX_ROWS))
    except slog.SlogUnavailable as e:
        return {"error": str(e), "rows": []}
    except slog.SlogError as e:
        return {"error": str(e), "rows": [], "query_file": str(QUERY_FILE)}
    return {"n_rows": d["n_rows"], "returned": d["returned"],
            "truncated": d["truncated"], "rows": d["rows"],
            "query_file": str(QUERY_FILE)}


@mcp.tool()
def name_curies(curies: list[str]) -> list[dict]:
    """Map result CURIEs to readable rows [{id, name, category}]."""
    return core.name_curies(curies)


if __name__ == "__main__":
    mcp.run()
