import hashlib
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import kg2_core as core
import mr_stats as stats
import slog_client as slog
from mr_logging import (RULE, SESSION_DIR, banner, csv_row, fmt_dur, full_list,
                        get_logger, next_seq, preview, save_query, step, table,
                        tool_call)

INSTRUCTIONS = (Path(__file__).resolve().parent / "instructions" / "kg2.md").read_text()
MAX_ROWS = 500
OUTPUT_REL = "result"
QUERY_FILE = Path(os.environ.get(
    "KG2_QUERY_FILE",
    Path(__file__).resolve().parent.parent / "slog" / "query.slog"))

log = get_logger("server")

mcp = FastMCP("kg2", instructions=INSTRUCTIONS)

_last_slog_curies = []


@contextmanager
def _record(name, **params):
    if banner():
        log.info(f"query file: {QUERY_FILE}")
        log.info(f"slog server: {slog.HOST}:{slog.PORT} (client timeout {slog.TIMEOUT_S}s)")
        log.info(f"node DB: {core.NODE_DB}")
        log.info(RULE)
    row = {"tool": name, "seq": next_seq(),
           "ts_start": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
    t0 = time.perf_counter()
    try:
        with tool_call(log, name, **params):
            yield row
        row.setdefault("status", "ok")
    except Exception as e:
        row["status"] = "error"
        row.setdefault("error", f"{type(e).__name__}: {e}"[:300])
        raise
    finally:
        row["wall_s"] = time.perf_counter() - t0
        http_s, http_calls = core.take_http_stats()
        if http_calls:
            row.setdefault("http_s", http_s)
            row.setdefault("http_calls", http_calls)
        rss, avail = stats.env_snapshot()
        row.setdefault("slogd_rss_gb", rss)
        row.setdefault("mem_avail_gb", avail)
        predicted = row.get("predicted_s")
        if predicted:
            row["cost_ratio"] = round(row["wall_s"] / predicted, 2)
        csv_row(**row)


def _curie_columns(rows):
    seen = []
    for row in rows:
        for cell in (row if isinstance(row, (list, tuple)) else [row]):
            s = str(cell)
            if ":" in s and not s.startswith("(") and s not in seen:
                seen.append(s)
    return seen


@mcp.tool()
def list_predicates() -> list[str]:
    """Valid RTX-KG2 biolink predicates (e.g. 'biolink:treats'), most-frequent first."""
    with _record("list_predicates") as row:
        preds = core.load_predicates()
        log.info(f"  top predicates: {preview(preds, 5)}")
        row["n_out"] = len(preds)
        return preds


@mcp.tool()
def resolve_entity(term: str, limit: int = 10, biolink_type: str = "") -> list[dict]:
    """Resolve an entity mention to candidate concepts; ask the user if the senses are ambiguous."""
    with _record("resolve_entity", term=term, limit=limit,
                 biolink_type=biolink_type or None) as row:
        hits = core.resolve_term(term, limit=limit, biolink_type=biolink_type or None)
        log.info(f"  candidates for {term!r}:")
        table(log, ["id", "name", "category", "score"],
              [(h["id"], h["name"], h["category"], h["score"]) for h in hits],
              limit=limit)
        row["term"] = term
        row["n_out"] = len(hits)
        if not hits:
            row["notes"] = "no-candidates"
        return hits


@mcp.tool()
def expand_entity(curies: list[str]) -> dict:
    """Expand chosen CURIEs to the exact KG2 id set to match in a query."""
    with _record("expand_entity", n_curies=len(curies)) as row:
        full_list(log, "input CURIEs", curies)
        combined = []
        for cid in curies:
            with step(log, f"expand {cid}"):
                combined.extend(core.expand_to_kg2(cid))
        kg2_ids = list(dict.fromkeys(combined))
        log.info(f"  {len(curies)} input CURIE(s) -> {len(kg2_ids)} distinct KG2 id(s)")
        full_list(log, "kg2_ids", kg2_ids)
        row["n_in"] = len(curies)
        row["n_out"] = len(kg2_ids)
        if not kg2_ids:
            row["notes"] = "expanded-to-nothing"
        return {"kg2_ids": kg2_ids}


@mcp.tool()
def run_slog(limit: int = MAX_ROWS) -> dict:
    """Run the Slog program you have written to slog/query.slog.

    Write your program to that file first (with Write or Edit), then call this. It takes
    no program argument -- it always runs whatever is currently in the file, so the file
    is the record of what ran.

    The answer relation must be declared and named `result`. It is dropped before the
    program runs, so each query starts from an empty answer relation.

    The session is already warm, so a query costs a compile plus evaluation. Returns
    {n_rows, returned, truncated, rows, query_file}.
    """
    global _last_slog_curies
    with _record("run_slog", limit=limit) as row:
        row["query_file"] = str(QUERY_FILE)
        if not QUERY_FILE.exists():
            log.error(f"  x query file {QUERY_FILE} does not exist")
            row["status"] = "error"
            row["error"] = "query file does not exist"
            return {"error": f"{QUERY_FILE} does not exist -- write your Slog program there "
                             f"first, then call run_slog again", "rows": []}

        program = QUERY_FILE.read_text()
        mtime = datetime.fromtimestamp(QUERY_FILE.stat().st_mtime)
        n_tables, n_derived = stats.parse_program(program)
        row["program_bytes"] = len(program)
        row["program_sha8"] = hashlib.sha256(program.encode()).hexdigest()[:8]
        row["n_tables_declared"] = n_tables
        row["n_derived_rels"] = n_derived
        archived = save_query(row["seq"], program)
        log.info(f"  query file {QUERY_FILE} "
                 f"({len(program)} bytes, modified {mtime:%Y-%m-%d %H:%M:%S})")
        if archived:
            log.info(f"  archived as {archived.relative_to(SESSION_DIR)}")
        log.info(f"  shape: {n_tables} table(s) declared, {n_derived} derived relation(s) "
                 f"-- expect ~{stats.PER_STRATUM_S:.0f}s per derived relation")
        log.info("  program:\n" + "\n".join(f"    | {ln}" for ln in program.splitlines()))

        before_build = None
        before_stats = None
        t_start = None
        t_total = time.perf_counter()
        try:
            t0 = time.perf_counter()
            try:
                slog.drop(OUTPUT_REL)
                log.info(f"  dropped previous `{OUTPUT_REL}` relation")
            except slog.SlogError as e:
                log.info(f"  no previous `{OUTPUT_REL}` to drop ({e})")
            row["drop_s"] = time.perf_counter() - t0

            before_stats = stats.stat_snapshot()
            before_build = stats.build_snapshot()
            t_start = time.time()

            t0 = time.perf_counter()
            with step(log, "slog run"):
                slog.run_file(QUERY_FILE)
            row["run_s"] = time.perf_counter() - t0

            t0 = time.perf_counter()
            with step(log, f"dump `{OUTPUT_REL}` (limit {min(limit, MAX_ROWS)})"):
                d = slog.dump(OUTPUT_REL, limit=min(limit, MAX_ROWS))
            row["dump_s"] = time.perf_counter() - t0
        except slog.SlogUnavailable as e:
            log.error(f"  x slog server unavailable: {e}")
            row["status"] = "error"
            row["error"] = f"slog unavailable: {e}"[:300]
            return {"error": str(e), "rows": []}
        except slog.SlogError as e:
            log.error(f"  x slog error: {e}")
            row["status"] = "error"
            row["error"] = f"slog error: {e}"[:300]
            return {"error": str(e), "rows": [], "query_file": str(QUERY_FILE)}

        total = time.perf_counter() - t_total
        n_compiled, compile_s = stats.build_delta(before_build, t_start)
        row["n_strata_compiled"] = n_compiled
        row["compile_s"] = compile_s
        if compile_s is not None:
            row["exec_s"] = max(0.0, row.get("run_s", 0.0) - compile_s)
        row.update(stats.stat_delta(before_stats))
        row["predicted_s"] = stats.predict(n_derived, bool(n_compiled))

        notes = []
        if n_compiled == 0:
            notes.append("compile-cached")
        log.info(f"  timing: total={fmt_dur(total)}  "
                 f"compile={fmt_dur(compile_s) if compile_s is not None else '?'}  "
                 f"exec={fmt_dur(row['exec_s']) if row.get('exec_s') is not None else '?'}  "
                 f"(strata compiled={n_compiled}, executed={row.get('n_strata_executed')})")
        if row.get("fixpoint_ms") is not None:
            log.info(f"  daemon: fixpoint={row['fixpoint_ms']}ms  "
                     f"iterations={row['iterations']}  rule_fires={row['rule_fires']}")
        if row.get("predicted_s"):
            log.info(f"  cost model predicted ~{row['predicted_s']:.0f}s for this shape")

        log.info(f"  result: n_rows={d['n_rows']} returned={d['returned']} "
                 f"truncated={d['truncated']}")
        row["n_rows"] = d["n_rows"]
        row["returned"] = d["returned"]
        row["truncated"] = d["truncated"]

        curies = _curie_columns(d["rows"])
        _last_slog_curies = curies
        row["n_curies"] = len(curies)
        log.info("  CURIEs out of the answer relation, unnamed at this point:")
        full_list(log, "result CURIEs", curies)

        if d["n_rows"] == 0:
            notes.append("zero-rows")
            log.warning("  !! the query returned no rows -- if you joined two derived "
                        "sets, check kg2_norm before assuming the biology is absent")
        if d["truncated"]:
            notes.append("truncated")
            log.warning(f"  !! truncated: {d['n_rows']} rows exist, only "
                        f"{d['returned']} returned (limit {min(limit, MAX_ROWS)})")
        if row.get("run_s", 0) > 120:
            notes.append("slow-run")
        row["notes"] = " ".join(notes)

        return {"n_rows": d["n_rows"], "returned": d["returned"],
                "truncated": d["truncated"], "rows": d["rows"],
                "query_file": str(QUERY_FILE)}


@mcp.tool()
def name_curies(curies: list[str]) -> list[dict]:
    """Map result CURIEs to readable rows [{id, name, category}]."""
    with _record("name_curies", n_curies=len(curies)) as row:
        log.info("  CURIEs to name:")
        full_list(log, "input", curies)
        if _last_slog_curies:
            overlap = len(set(curies) & set(_last_slog_curies))
            log.info(f"  {overlap}/{len(_last_slog_curies)} of the CURIEs from the last "
                     f"run_slog are being named here")

        named = core.name_curies(curies)

        log.info(f"  {len(named)} CURIE(s) resolved to names:")
        table(log, ["id", "name", "category"],
              [(r["id"], r["name"], r["category"]) for r in named], limit=len(named))
        by_cat = {}
        for r in named:
            by_cat[r["category"] or "(none)"] = by_cat.get(r["category"] or "(none)", 0) + 1
        log.info("  by category: " + ", ".join(
            f"{c}={n}" for c, n in sorted(by_cat.items(), key=lambda kv: -kv[1])))

        resolved = {r["id"] for r in named}
        unresolved = [c for c in curies if c not in resolved]
        if unresolved:
            full_list(log, "unresolved (no row in the node DB)", unresolved)
        row["n_in"] = len(curies)
        row["n_out"] = len(named)
        row["n_unresolved"] = len(unresolved)
        if unresolved:
            row["notes"] = "unresolved-curies"
        return named


if __name__ == "__main__":
    mcp.run()
