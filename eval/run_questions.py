#!/usr/bin/env python3
"""Ask Claude Code a list of questions and record exactly what happened.

    python eval/run_questions.py                     # uses eval/questions.txt
    python eval/run_questions.py my_questions.txt

For each question it runs one `claude -p` in this project directory, so the MR MCP
server starts automatically from .mcp.json. Each run gets a fresh MCP process but
they all reuse the same warm Slog session, so the KG loads at most once.

Per question you get:
  eval/runs/<stamp>/qNN.jsonl    the raw stream-json event log
  eval/runs/<stamp>/qNN.md       question, Slog programs written, answer
  eval/runs/<stamp>/summary.tsv  one row per question

Prerequisite: the Slog session server must be running (slog/kg2-server.sh).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
TOOLS = ["list_predicates", "resolve_entity", "expand_entity", "run_slog", "name_curies"]
# Write/Edit/Read are required: the Slog program is written to slog/query.slog by Claude
# itself, and run_slog executes whatever is in that file.
ALLOWED = [f"mcp__MR__{t}" for t in TOOLS] + ["Write", "Edit", "Read"]
TIMEOUT_S = int(os.environ.get("EVAL_TIMEOUT", "1800"))


def available_ram_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(int(line.split()[1]) / 1048576)
    except OSError:
        return None
    return None


def preflight():
    """Check the session server is listening; every question fails without it."""
    import socket
    port = int(os.environ.get("SLOG_SERVER_PORT", "8642"))
    try:
        socket.create_connection(("127.0.0.1", port), timeout=5).close()
        print(f"session server up on :{port}, {available_ram_gb()} GB free", flush=True)
    except OSError as e:
        print(f"WARNING: nothing listening on 127.0.0.1:{port} ({e})", flush=True)
        print("  Start it with slog/kg2-server.sh, or every question will fail.", flush=True)
        if input("  continue anyway? [y/N] ").strip().lower() != "y":
            sys.exit(1)


def read_questions(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def parse_events(lines):
    """Pull the interesting parts out of a stream-json log."""
    calls, answer, cost, turns, denials, err = [], None, None, None, [], None
    pending = {}
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    pending[block.get("id")] = {"tool": block.get("name"),
                                                "input": block.get("input", {})}
        elif t == "user":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    call = pending.pop(block.get("tool_use_id"), {"tool": "?", "input": {}})
                    call["result"] = block.get("content")
                    calls.append(call)
        elif t == "result":
            answer = ev.get("result")
            cost = ev.get("total_cost_usd")
            turns = ev.get("num_turns")
            denials = ev.get("permission_denials") or []
            if ev.get("is_error"):
                err = ev.get("subtype") or "error"
    calls.extend(pending.values())          # calls with no result (timeout/denial)
    return {"calls": calls, "answer": answer, "cost": cost, "turns": turns,
            "denials": denials, "error": err}


def result_field(res, key):
    """run_slog returns JSON inside the tool_result content; dig out one field."""
    text = res if isinstance(res, str) else json.dumps(res)
    try:
        # content is often [{"type":"text","text":"{...}"}]
        if isinstance(res, list):
            text = "".join(b.get("text", "") for b in res if isinstance(b, dict))
        obj = json.loads(text)
        return obj.get(key)
    except Exception:
        return None


def query_file_content(call):
    """The new query.slog contents if this call wrote it, else None.

    Claude writes the program to the file itself, so the program text lives in a Write
    (or Edit) call rather than in run_slog's arguments.
    """
    tool = call.get("tool") or ""
    inp = call.get("input") or {}
    if "query.slog" not in str(inp.get("file_path", "")):
        return None
    if tool == "Write":
        return inp.get("content")
    if tool == "Edit":
        return f";; (Edit) replaced:\n;;   {inp.get('old_string', '')[:120]}\n\n{inp.get('new_string', '')}"
    return None


def write_programs(outdir, tag, parsed):
    """Save each generated program as its own .slog file, so it can be rerun as-is.

    Header comments record which question produced it and what came back, since a
    program that returned 0 rows is as interesting as one that worked.
    """
    written = []
    n = 0
    pending = None
    for c in parsed["calls"]:
        tool = c.get("tool") or ""
        prog = query_file_content(c)
        if prog is not None:
            # remember the newest version of query.slog; the next run_slog ran this
            pending = prog
            continue
        if not tool.endswith("run_slog"):
            continue
        n += 1
        rows = result_field(c.get("result"), "n_rows")
        err = result_field(c.get("result"), "error")
        head = [f";; {tag} step {n}"]
        if err:
            head.append(f";; ERROR: {err}")
        else:
            head.append(f";; n_rows={rows}")
        path = outdir / f"{tag}-step{n}.slog"
        path.write_text("\n".join(head) + "\n\n"
                        + (pending or ";; (program not captured)").strip() + "\n")
        written.append(path.name)
    return written


def write_report(path, question, parsed):
    lines = [f"# {question}", ""]
    if parsed["error"]:
        lines += [f"**run error:** {parsed['error']}", ""]
    if parsed["denials"]:
        lines += [f"**permission denials:** {json.dumps(parsed['denials'])}", ""]
    lines += ["## Tool calls", ""]
    for c in parsed["calls"]:
        tool = (c.get("tool") or "?").replace("mcp__MR__", "")
        lines.append(f"### {tool}")
        prog = query_file_content(c)
        if prog:
            lines += ["", "```slog", prog.strip(), "```", ""]
        else:
            lines += ["", "```json", json.dumps(c.get("input"), indent=2)[:800], "```", ""]
        n = result_field(c.get("result"), "n_rows")
        err = result_field(c.get("result"), "error")
        if err:
            lines += [f"ERROR: {err}", ""]
        elif n is not None:
            lines += [f"n_rows={n}", ""]
    lines += ["## Answer", "", parsed["answer"] or "(none)", ""]
    Path(path).write_text("\n".join(lines))


def main():
    qfile = sys.argv[1] if len(sys.argv) > 1 else HERE / "questions.txt"
    questions = read_questions(qfile)
    if not questions:
        sys.exit(f"no questions found in {qfile}")
    print(f"{len(questions)} question(s) from {qfile}")
    preflight()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = HERE / "runs" / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    summary = outdir / "summary.tsv"
    with summary.open("w") as f:
        f.write("n\tsecs\tturns\tcost_usd\ttool_calls\tslog_runs\terrors\t"
                "max_rows\tdenied\tstatus\tquestion\n")

    min_free = int(os.environ.get("EVAL_MIN_FREE_GB", "60"))

    for i, q in enumerate(questions, 1):
        # slogd RSS grows per query and dropping relations does not return it, so
        # check before each question rather than trusting SLOG_MEM_MAX -- the soft
        # cap has been observed growing straight through into swap.
        free = available_ram_gb()
        if free is not None and free < min_free:
            print(f"\nSTOPPING: only {free} GB free (need {min_free}). "
                  f"Restart the session server to reclaim it; "
                  f"{len(questions) - i + 1} question(s) not run.", flush=True)
            break

        tag = f"q{i:02d}"
        print(f"\n[{tag}] {q}", flush=True)
        raw = outdir / f"{tag}.jsonl"
        t0 = time.time()
        timed_out = False

        # Stream straight to the file rather than buffering: a question that times
        # out or is interrupted still leaves everything it produced on disk.
        with raw.open("w") as out, (outdir / f"{tag}.stderr").open("w") as errf:
            proc = subprocess.Popen(
                ["claude", "-p", q, "--output-format", "stream-json", "--verbose",
                 "--allowedTools", *ALLOWED],
                cwd=PROJECT, stdout=out, stderr=errf, text=True)
            try:
                proc.wait(timeout=TIMEOUT_S)
            except subprocess.TimeoutExpired:
                # One slow question must not abort the remaining ones
                timed_out = True
                proc.kill()
                proc.wait()
                print(f"  TIMEOUT after {TIMEOUT_S}s -- partial output kept, continuing",
                      flush=True)
        secs = time.time() - t0
        if not (outdir / f"{tag}.stderr").stat().st_size:
            (outdir / f"{tag}.stderr").unlink()

        p = parse_events(raw.read_text().splitlines())
        if timed_out:
            p["error"] = f"timeout after {TIMEOUT_S}s"
        write_report(outdir / f"{tag}.md", q, p)
        progs = write_programs(outdir, tag, p)

        slog_calls = [c for c in p["calls"] if (c.get("tool") or "").endswith("run_slog")]
        errors = sum(1 for c in slog_calls if result_field(c.get("result"), "error"))
        rows = [result_field(c.get("result"), "n_rows") for c in slog_calls]
        rows = [r for r in rows if isinstance(r, int)]
        with summary.open("a") as f:
            f.write(f"{tag}\t{secs:.0f}\t{p['turns']}\t{p['cost']}\t{len(p['calls'])}\t"
                    f"{len(slog_calls)}\t{errors}\t{max(rows) if rows else 0}\t"
                    f"{len(p['denials'])}\t{'TIMEOUT' if timed_out else 'ok'}\t{q}\n")
        print(f"  {secs:.0f}s  {len(p['calls'])} tool calls, {len(slog_calls)} slog runs, "
              f"{errors} errors, max_rows={max(rows) if rows else 0}"
              + (f", programs: {', '.join(progs)}" if progs else ""), flush=True)
        if p["denials"]:
            print(f"  DENIED: {json.dumps(p['denials'])[:200]}", flush=True)

    print(f"\ndone -> {outdir}")
    print(f"  summary: {summary}")
    print(f"  per question: {outdir}/qNN.md")


if __name__ == "__main__":
    main()
