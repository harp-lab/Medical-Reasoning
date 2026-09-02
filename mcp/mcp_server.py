import hashlib
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import kg2_core as core
import mr_plan as plan
import mr_stats as stats
import slog_client as slog
from mr_logging import (RULE, SESSION_DIR, banner, csv_row, fmt_dur, full_list,
                        get_logger, next_seq, preview, save_plan, save_query,
                        step, table, tool_call)

INSTRUCTIONS = (Path(__file__).resolve().parent / "instructions" / "kg2.md").read_text()
# Hard ceiling on rows handed back, whatever `limit` the caller asks for -- both dump
# sites clamp with min(limit, MAX_ROWS), so this is the enforcement and not a default.
# `n_rows` still reports the true count, so a truncated answer stays honest.
MAX_ROWS = int(os.environ.get("KG2_MAX_ROWS", "50"))
OUTPUT_REL = "result"
QUERY_FILE = Path(os.environ.get(
    "KG2_QUERY_FILE",
    Path(__file__).resolve().parent.parent / "slog" / "query.slog"))

log = get_logger("server")

mcp = FastMCP("kg2", instructions=INSTRUCTIONS)

_last_slog_curies = []
# One question is meant to cost one run (mcp/instructions/kg2.md, "One question, one
# run").  Counting them does not block a second run -- the permission prompt is the
# gate -- but it puts every repeat in summary.csv where it can be seen after the fact.
_slog_runs = 0


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
    """Run the Slog program you have written to slog/query.slog. ONE RUN PER QUESTION.

    Write your program to that file first (with Write or Edit), then call this in the same
    turn. Do NOT ask the user in prose whether to run it -- this tool is gated by a
    permission prompt, and that prompt is where they say yes or no; asking first makes them
    answer twice. This takes no program argument; it always runs whatever is currently in
    the file, so the file is the record of what ran.

    This call costs minutes of wall clock and tens of GB on a shared machine. Do not call
    it twice for the same question. If it fails, report `query failed` with the error and
    stop. If the answer is truncated or empty, report that and stop. A failure, a
    truncation, and a zero-row answer are all final results, not prompts to rewrite the
    program and try again -- only the user decides that.

    The answer relation must be declared and named `result`. It is dropped before the
    program runs, so each query starts from an empty answer relation.

    At most 50 rows come back, whatever `limit` you pass -- `limit` can only ask for
    FEWER. `n_rows` is the true count, so report `n_rows rows, showing 50` and display
    the 50. Never display more rows than you were given, and never re-run to see the rest.

    Returns {n_rows, returned, truncated, rows, query_file}.
    """
    global _last_slog_curies, _slog_runs
    _slog_runs += 1
    with _record("run_slog", limit=limit) as row:
        row["query_file"] = str(QUERY_FILE)
        row["slog_run_n"] = _slog_runs
        if _slog_runs > 1:
            log.warning(f"  !! this is run #{_slog_runs} of this session -- if it is a "
                        f"retry of the same question rather than a new question, that is "
                        f"minutes of wall clock the one-run-per-question rule exists to "
                        f"prevent (mcp/instructions/kg2.md)")
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
                resp = slog.run_file(QUERY_FILE)
            row["run_wall_s"] = time.perf_counter() - t0

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
        row.update(stats.stat_delta(before_stats))
        row.update(stats.work_delta(before_stats))
        # Everything the daemon spent OUTSIDE its read loop:
        #   setup_s = run_wall_s - fixpoint_ms/1000
        # fixpoint_ms is the daemon's own read-loop accounting -- the only part of
        # the run it reports.  The remainder is stratum attach plus, dominant on
        # this KG, the whole-DB reload armed after every fixpoint (daemon.h:609 ->
        # database.h reloadInsertBatches): it re-stages every relation as delta and
        # clears every index for the incoming stratum to re-intern.  That runs as
        # its own internal stratum, so it emits no pause line and lands in no ms.
        #
        # compile_s is deliberately NOT subtracted.  It measures elapsed time until
        # the freshly built .so appeared, and the daemon is already working by then
        # (the stratum reaches it in ~0.3s while clang runs on), so clang overlaps
        # setup rather than adding to it -- wall time here is max(), not sum().
        if row.get("fixpoint_ms") is not None:
            row["setup_s"] = max(0.0, row.get("run_wall_s", 0.0)
                                 - row["fixpoint_ms"] / 1000.0)
        row["predicted_s"] = stats.predict(n_derived, bool(n_compiled))

        notes = []
        if n_compiled == 0:
            notes.append("compile-cached")

        # The join plan this query actually ran under: which relation drove each
        # rule and in what order the tail joined.  summary.csv gets the digest;
        # the full per-rule listing is archived beside the query.
        try:
            pinfo = plan.collect(resp)
        except Exception as e:
            log.warning(f"  !! could not recover the join plan: {e!r}")
            pinfo = None
        if pinfo:
            row.update(pinfo["csv"])
            log.info("  join plan:\n" + "\n".join(
                f"  {ln}" for ln in plan.render(pinfo).splitlines()))
            archived_plan = save_plan(row["seq"], plan.render(pinfo))
            if archived_plan:
                log.info(f"  archived as {archived_plan.relative_to(SESSION_DIR)}")
            if not pinfo["plans"]:
                notes.append("no-plan")
                log.warning("  !! no (fixpoint ...) events came back -- either the "
                            "slog server predates the plan-reporting change or "
                            "every stratum was already resident")
            elif pinfo["csv"]["n_arms"] == 0 and pinfo["env"].get("multiplan"):
                notes.append("no-arms")
                log.warning(
                    f"  !! SLOG_MULTIPLAN is on "
                    f"(index={pinfo['env'].get('multiplan_index') or '?'}) but not "
                    f"one rule-def in these plans carries an arm mark, so runtime "
                    f"plan selection had nothing to choose between and cannot be "
                    f"what moved the timing.  slog's arm-eligibility gate "
                    f"(join-planning.rkt arm-flavor-ok?) needs >= 3 body join "
                    f"clauses in a rule; the orders above show how many each has")
        log.info(f"  timing: total={fmt_dur(total)}  "
                 f"compile={fmt_dur(compile_s) if compile_s is not None else '?'}  "
                 f"setup={fmt_dur(row['setup_s']) if row.get('setup_s') is not None else '?'}  "
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
        if row.get("run_wall_s", 0) > 120:
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
