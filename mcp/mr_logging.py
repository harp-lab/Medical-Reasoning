import csv
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.environ.get("KG2_LOG_DIR", PROJECT_DIR / "logs"))

SESSION_ID = datetime.now().strftime("%Y%m%d-%H%M%S")
SESSION_DIR = LOG_DIR / SESSION_ID
LOG_FILE = SESSION_DIR / "mcp.log"
CSV_FILE = SESSION_DIR / "summary.csv"
QUERY_DIR = SESSION_DIR / "queries"

FIELDS = (
    "ts_start", "session_id", "seq", "tool", "status", "wall_s", "notes", "error",
    "query_file", "program_sha8", "program_bytes",
    "n_tables_declared", "n_derived_rels",
    "n_strata_compiled", "n_strata_executed", "compile_s", "exec_s",
    "drop_s", "run_s", "dump_s",
    "fixpoint_ms", "iterations", "rule_fires",
    "predicted_s", "cost_ratio",
    "n_rows", "returned", "truncated", "n_curies",
    "term", "n_in", "n_out", "n_unresolved", "http_s", "http_calls",
    "slogd_rss_gb", "mem_avail_gb",
)

PREVIEW_N = int(os.environ.get("KG2_LOG_PREVIEW", "10"))
LEVEL = os.environ.get("KG2_LOG_LEVEL", "INFO").upper()

RULE = "=" * 78
THIN = "-" * 78

_configured = False
_banner_done = False
_seq = 0


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


class _LazyFileHandler(logging.FileHandler):

    def _open(self):
        _ensure_dir()
        return super()._open()


class _Formatter(logging.Formatter):

    def format(self, record):
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        name = record.name.split(".")[-1]
        head = f"{ts} | {record.levelname:<7} | {name:<13} | "
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        pad = " " * len(head)
        body = text.replace("\n", "\n" + pad)
        return head + body


def _configure():
    global _configured
    if _configured:
        return

    root = logging.getLogger("mr")
    root.setLevel(LEVEL)
    root.propagate = False

    fh = _LazyFileHandler(LOG_FILE, encoding="utf-8", delay=True)
    fh.setFormatter(_Formatter())
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(_Formatter())
    root.addHandler(sh)

    _configured = True


def banner():
    global _banner_done
    if _banner_done:
        return False
    _banner_done = True
    _configure()
    root = logging.getLogger("mr")
    root.info(RULE)
    root.info(f"KG2 MCP session {SESSION_ID} starting")
    root.info(f"pid={os.getpid()}  python={sys.version.split()[0]}")
    root.info(f"session dir : {SESSION_DIR}")
    return True


def get_logger(name):
    _configure()
    return logging.getLogger(f"mr.{name}")


def fmt_dur(seconds):
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m {s:04.1f}s"


def preview(items, n=PREVIEW_N):
    items = list(items)
    if not items:
        return "(empty)"
    shown = ", ".join(str(x) for x in items[:n])
    extra = len(items) - n
    return shown + (f"  ... +{extra} more" if extra > 0 else "")


def table(log, headers, rows, limit=PREVIEW_N):
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    shown = rows[:limit]
    widths = [len(h) for h in headers]
    for r in shown:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], min(len(c), 60))

    def line(cells):
        return "  ".join(
            (c[:57] + "...") if len(c) > 60 else c.ljust(widths[i])
            for i, c in enumerate(cells))

    log.info(line(headers))
    log.info("  ".join("-" * w for w in widths))
    for r in shown:
        log.info(line(r))
    if len(rows) > len(shown):
        log.info(f"... +{len(rows) - len(shown)} more rows")


def full_list(log, label, items, per_line=4):
    items = [str(x) for x in items]
    if not items:
        log.info(f"  {label}: (empty)")
        return
    log.info(f"  {label} ({len(items)}):")
    width = max((len(x) for x in items), default=0)
    for i in range(0, len(items), per_line):
        log.info("    " + "  ".join(x.ljust(width) for x in items[i:i + per_line]).rstrip())


def save_query(seq, text, tool="run_slog"):
    _configure()
    path = QUERY_DIR / f"{seq:03d}_{tool}.slog"
    try:
        QUERY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    except Exception as e:
        logging.getLogger("mr.query").warning(f"could not archive query: {e!r}")
        return None


def next_seq():
    global _seq
    _seq += 1
    return _seq


def _fmt_cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def csv_row(**fields):
    _configure()
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise KeyError(f"unknown summary column(s): {sorted(unknown)}")
    fields.setdefault("session_id", SESSION_ID)
    try:
        _ensure_dir()
        new = not CSV_FILE.exists()
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(FIELDS)
            w.writerow([_fmt_cell(fields.get(c)) for c in FIELDS])
    except Exception as e:
        logging.getLogger("mr.csv").warning(f"could not write summary row: {e!r}")


@contextmanager
def step(log, label, level=logging.INFO):
    log.log(level, f"  * {label} ...")
    t0 = time.perf_counter()
    try:
        yield
    except Exception:
        log.error(f"  x {label} FAILED after {fmt_dur(time.perf_counter() - t0)}")
        raise
    log.log(level, f"  + {label} done in {fmt_dur(time.perf_counter() - t0)}")


@contextmanager
def tool_call(log, name, **params):
    args = "  ".join(f"{k}={v!r}" for k, v in params.items())
    log.info(THIN)
    log.info(f">> TOOL {name}  {args}".rstrip())
    t0 = time.perf_counter()
    try:
        yield
    except Exception:
        log.exception(f"XX TOOL {name} raised after {fmt_dur(time.perf_counter() - t0)}")
        raise
    finally:
        elapsed = time.perf_counter() - t0
        log.info(f"<< TOOL {name} finished in {fmt_dur(elapsed)}")
        if elapsed > 30:
            log.warning(f"!! {name} took {fmt_dur(elapsed)} -- slow call")
        log.info(THIN)
