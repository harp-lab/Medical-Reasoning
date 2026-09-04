"""Where every number in summary.csv comes from.

A summary row mixes four very different kinds of number in one flat CSV, and the
CSV gives no hint which is which: `fixpoint_ms` is the daemon's own accounting,
`compile_s` is a file mtime, `predicted_s` is a constant times a regex count.
They print identically and they are not equally trustworthy.  Reading a row
without knowing the difference is how a fitted constant gets quoted as a
measurement.

So the mapping lives here as data, next to the code that fills the row, rather
than as prose in a doc that drifts.  `orion columns` prints it; `orion execute
-v` tags every number it reports with the same SOURCE keys.

Keep this in sync with mr_logging.FIELDS -- orion's self-check compares them and
complains about either direction of drift.
"""

# Ordered worst-to-best for "how directly did slog tell us this", because that is
# the axis that matters when reading a row: a `daemon` number is an observation,
# a `model` number is an assumption wearing the same clothes.
SOURCES = {
    "daemon": "slogd itself -- its $stat_* relations, or a line it emitted",
    "session": "slog_server.rkt, the Racket wrapper holding the session",
    "build":   "files the slog COMPILER left in slog/build/",
    "client":  "measured in Python, here, around the request",
    "program": "parsed out of the .slog text with a regex",
    "model":   "a hardcoded constant -- an assumption, NOT a measurement of this run",
    "os":      "read out of /proc",
}

# (column, source, how it is arrived at)
COLUMNS = [
    ("ts_start", "client", "wall clock when the call started"),
    ("session_id", "client", "log-session timestamp"),
    ("seq", "client", "call counter within this process"),
    ("tool", "client", "which entry point ran"),
    ("status", "client", "ok / error"),
    ("wall_s", "client", "perf_counter around the whole call"),
    ("notes", "client", "flags set here: zero-rows, truncated, slow-run, no-plan, ..."),
    ("error", "client", "exception text, truncated to 300 chars"),

    ("query_file", "client", "path that was run"),
    ("slog_run_n", "client", "how many runs this process has made"),
    ("program_sha8", "program", "sha256 of the program text, first 8 hex"),
    ("program_bytes", "program", "len(program)"),
    ("n_tables_declared", "program", r"count of /^\s*table\s*\(/ in the file"),
    ("n_derived_rels", "program", r"distinct heads of /^\s*rule\s*\(/ -- DISTINCT, so "
                                 "20 rules writing one relation count once"),

    ("n_strata_compiled", "build", "*.plan files that appeared in slog/build/ during the run"),
    ("n_strata_executed", "daemon", "$stat_fixpoint rows with pos > the pre-run high-water mark"),

    ("run_wall_s", "client", "perf_counter around the `run` request"),
    ("setup_s", "client", "run_wall_s - fixpoint_ms/1000.  A SUBTRACTION ACROSS TWO "
                          "CLOCKS (Python wall vs the daemon's microseconds); it is "
                          "the residual, so every unattributed cost lands in it"),
    ("compile_s", "build", "newest fresh .so mtime - run start.  Overlaps the run "
                           "rather than adding to it, so it is not a slice of run_wall_s"),
    ("drop_s", "client", "perf_counter around the `drop` request"),
    ("dump_s", "client", "perf_counter around the `dump` request"),

    ("fixpoint_ms", "daemon", "sum of $stat_fixpoint col 4 (microseconds) / 1000.  "
                              "The daemon's read loop ONLY -- stratum attach and the "
                              "post-fixpoint whole-DB reload are outside it"),
    ("iterations", "daemon", "sum of $stat_fixpoint col 3"),
    ("rule_fires", "daemon", "sum of per-(loc,tag) $stat_fires increases"),
    ("work_ticks", "daemon", "sum of $stat_work col 3 over rows new this run.  Only "
                             "INTERPRETED rules meter, so 0 means 'nothing interpreted', "
                             "not 'no work'"),
    ("work_rows", "daemon", "sum of $stat_work col 4 over the same rows"),
    ("work_top", "daemon", "the 6 heaviest of those rows, as loc|tag=ticks"),

    ("plan_hashes", "daemon", 'the HASH field of each (fixpoint SCC "HASH" ITERS MS) line'),
    ("join_plan", "build", "join orders read out of build/<hash>.plan -- what the "
                           "compiler decided, not what the daemon observed"),
    ("n_arms", "build", "rule-defs in those plans carrying (attrs (arm N GID))"),
    ("arms_picked", "daemon", "the daemon's own (arms (g GID ARM CONVERGED LOC) ...) line"),
    ("multiplan", "session", "SLOG_MULTIPLAN / SLOG_MULTIPLAN_INDEX as the server "
                             "process has them -- not as this process has them"),
    ("slog_opt", "session", "SLOG_OPT in the server process"),
    ("phase_ms", "session", "gaps between the Racket wrapper's OWN timestamps on daemon "
                            "lines.  The lines are the daemon's; the clock is not"),

    ("predicted_s", "model", "(9.0 if anything compiled) + 13.0 * n_derived_rels.  Both "
                             "constants are hardcoded in mr_stats.py from the numbers in "
                             "mcp/instructions/kg2.md; nothing about THIS run feeds them"),
    ("cost_ratio", "model", "wall_s / predicted_s -- a measurement over an assumption"),

    ("n_rows", "daemon", "(tupledone N) from the dump -- the true count, before any cap"),
    ("returned", "session", "rows the wrapper kept: min(n_rows, limit)"),
    ("truncated", "session", "n_rows > returned"),
    ("n_curies", "client", "result cells containing ':' -- a string heuristic, not a type"),

    ("term", "client", "resolve_entity's input"),
    ("n_in", "client", "input count for the non-slog tools"),
    ("n_out", "client", "output count for the non-slog tools"),
    ("n_unresolved", "client", "name_curies inputs with no row in the node DB"),
    ("http_s", "client", "time in NodeNormalizer HTTP calls"),
    ("http_calls", "client", "number of those calls"),

    ("slogd_rss_gb", "os", "/proc/<slogd pid>/statm, sampled AFTER the call returned"),
    ("mem_avail_gb", "os", "MemAvailable in /proc/meminfo, same moment"),
]

BY_COLUMN = {c: (src, how) for c, src, how in COLUMNS}


def source_of(column):
    """The SOURCES key for a summary column, or None if it is not one."""
    entry = BY_COLUMN.get(column)
    return entry[0] if entry else None
