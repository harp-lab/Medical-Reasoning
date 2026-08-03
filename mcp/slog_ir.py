"""Parse, validate and content-address Slog programs.

Two jobs, both aimed at not wasting a clang build:

  validate()  -- catch undeclared relations, arity mismatches and bad predicate
                 strings from the live schema, in milliseconds, before the
                 program is sent to Slog at all.

  canonical_hash() -- alpha-rename variables and normalise layout so the same
                 question asked twice hashes the same, which lets the caller
                 reuse an already-materialised result relation instead of
                 recomputing it. Exact match only; near-miss containment is
                 deliberately out of scope (see docs/STATUS.md).

Slog's surface syntax is s-expressions, so a ~50 line reader is enough; this is
not a full parser and does not try to be.
"""
import hashlib
import re

# The output relation every generated program must define. Renamed to a
# content-addressed name before the program is sent, so two different questions
# can never collide on it and the same question reuses its answer.
OUTPUT_REL = "result"


# ---- reader ---------------------------------------------------------------
def _tokenize(text):
    # strip ;; comments, keeping string literals intact
    out = []
    for line in text.splitlines():
        buf, in_str, esc = [], False, False
        for i, ch in enumerate(line):
            if in_str:
                buf.append(ch)
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                buf.append(ch)
            elif ch == ";":
                break
            else:
                buf.append(ch)
        out.append("".join(buf))
    src = "\n".join(out)
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', src)


def parse(text):
    """Text -> list of top-level s-expressions (nested lists of str)."""
    toks = _tokenize(text)
    stack, top = [], []
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            if not stack:
                raise ValueError("unbalanced ')' in program")
            done = stack.pop()
            (stack[-1] if stack else top).append(done)
        else:
            (stack[-1] if stack else top).append(t)
    if stack:
        raise ValueError("unbalanced '(' in program")
    return top


KEYWORDS = {"table", "rule", "<--", "-->", "include", "instantiate", "as",
            "demand", "lattice", "_"}


def _is_var(tok):
    """A variable is a plain identifier that isn't a keyword.

    Quoted strings, numbers, operators like `<--`, and `_` are not variables.
    Relation names also match this shape, so callers must exclude head position
    positionally -- see canonicalize().
    """
    return (isinstance(tok, str)
            and tok not in KEYWORDS
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", tok) is not None)


# ---- program shape --------------------------------------------------------
def declarations(forms):
    """{name: arity} from `table (name t1 t2 ...)` forms."""
    decls = {}
    for i, f in enumerate(forms):
        if f == "table" and i + 1 < len(forms) and isinstance(forms[i + 1], list):
            head = forms[i + 1]
            if head and isinstance(head[0], str):
                decls[head[0]] = len(head) - 1
    return decls


def goals(forms):
    """Every (relname arg...) goal appearing in a rule, as (name, arity)."""
    found = []

    def walk(node, inside_rule):
        if not isinstance(node, list):
            return
        if (node and isinstance(node[0], str)
                and inside_rule and node[0] not in ("=", "!=", "<", ">", "<=", ">=")):
            found.append((node[0], len(node) - 1))
        for child in node:
            walk(child, inside_rule)

    for i, f in enumerate(forms):
        if f == "rule":
            for j in range(i + 1, len(forms)):
                if forms[j] == "rule" or forms[j] == "table":
                    break
                if isinstance(forms[j], list):
                    walk(forms[j], True)
    return found


# Relations big enough that scanning one unfiltered is never what was meant.
BASE_RELATIONS = {"kg2_edges", "kg2_nodes", "kg2_node_synonym", "kg2_node_publication",
                  "edge", "edge_dir", "edge_rel", "node", "equiv"}


def _unconstrained(forms):
    """Reject a rule that scans a base relation with nothing bound.

    One observed run wrote `rule (result a b ... o) <-- (kg2_edges a b ... o)` and
    materialised all 56,965,146 edges, then timed out. Any genuine question binds at
    least one constant, so a body that touches only base relations and contains no
    constant at all is a mistake worth catching for free.
    """
    problems = []
    for i, f in enumerate(forms):
        if f != "rule":
            continue
        body = []
        for j in range(i + 1, len(forms)):
            if forms[j] in ("rule", "table"):
                break
            if isinstance(forms[j], list):
                body.append(forms[j])
        if len(body) < 2:            # head only: a fact, nothing to scan
            continue
        goals_only = body[1:]
        names = {g[0] for g in goals_only if g and isinstance(g[0], str)}
        if not names or not names <= BASE_RELATIONS:
            continue                 # touches a derived relation: already narrowed
        has_const = any(
            isinstance(a, str) and a.startswith('"')
            for g in goals_only for a in g[1:])
        if not has_const:
            problems.append(
                f"rule over {', '.join(sorted(names))} binds no constant -- this scans "
                f"the whole relation (tens of millions of rows). Bind a predicate, a "
                f"CURIE, or join against a narrower relation first.")
    return problems


def validate(program, live_schema, predicates=None):
    """Return a list of human-readable problems; empty means it's worth compiling.

    live_schema: [(name, arity)] from slog_client.schema()
    predicates:  valid biolink predicate strings, or None to skip that check
    """
    problems = []
    try:
        forms = parse(program)
    except ValueError as e:
        return [f"syntax: {e}"]

    live = dict(live_schema)
    decls = declarations(forms)

    for name, arity in decls.items():
        if name in live and live[name] != arity:
            problems.append(
                f"'{name}' is declared with arity {arity} but the session already "
                f"has it at arity {live[name]}")

    # Slog requires a `table` line in EVERY program that uses a relation, even one
    # the session already holds -- "live" is not a substitute for declaring it.
    for name, arity in goals(forms):
        if name.startswith('"'):
            continue
        if name not in decls:
            extra = (" (it is live in the session, but each program must still "
                     "declare it)") if name in live else ""
            problems.append(
                f"relation '{name}' is not declared in this program -- add "
                f"`table ({name} ...)`{extra}")
        elif decls[name] != arity:
            problems.append(
                f"'{name}' used with {arity} columns but declared with {decls[name]}")

    problems.extend(_unconstrained(forms))

    if OUTPUT_REL not in decls and OUTPUT_REL not in live:
        problems.append(f"no `table ({OUTPUT_REL} ...)` -- the answer relation must be "
                        f"declared and named '{OUTPUT_REL}'")

    if predicates:
        valid = set(predicates)
        for tok in re.findall(r'"(biolink:[^"]+)"', program):
            if tok not in valid:
                problems.append(f"'{tok}' is not a valid KG2 predicate "
                                f"(see list_predicates)")
    return problems


# ---- content addressing ---------------------------------------------------
def canonicalize(program):
    """Alpha-rename variables and flatten layout, so equivalent programs match.

    Variables are renamed in first-appearance order (v0, v1, ...). Constants,
    relation names and arities are preserved verbatim -- `(edge d p "X")` and
    `(edge d p "Y")` must NOT collapse.
    """
    forms = parse(program)
    mapping = {}

    def rename(tok):
        if _is_var(tok):
            if tok not in mapping:
                mapping[tok] = f"v{len(mapping)}"
            return mapping[tok]
        return tok

    def canon(node):
        """Element 0 of any goal is a relation name or operator: keep it verbatim,
        or `(edge x y)` and `(node x y)` would collapse to one hash."""
        if not isinstance(node, list):
            return rename(node)
        if not node:
            return []
        return [node[0]] + [canon(c) for c in node[1:]]

    def render(node):
        if isinstance(node, list):
            return "(" + " ".join(render(c) for c in node) + ")"
        return node

    out, i = [], 0
    while i < len(forms):
        f = forms[i]
        # `table (name type ...)` is all names and types -- never renamed
        if f == "table" and i + 1 < len(forms) and isinstance(forms[i + 1], list):
            out.extend(["table", forms[i + 1]])
            i += 2
            continue
        out.append(canon(f) if isinstance(f, list) else f)
        i += 1
    return " ".join(render(f) for f in out)


def canonical_hash(program, deps=()):
    """Stable id for a program. `deps` folds in anything the text doesn't capture
    -- notably the contents of entity fact sets, since the same rule text over a
    different CURIE list is a different question."""
    h = hashlib.sha256()
    h.update(canonicalize(program).encode())
    for d in sorted(deps):
        h.update(b"\x00")
        h.update(str(d).encode())
    return h.hexdigest()[:16]


def rewrite_output(program, new_name):
    """Rename the OUTPUT_REL token to a content-addressed name.

    Word-boundary match so `result` is replaced but `result_set` is not, and
    quoted strings containing the word are left alone.
    """
    parts = re.split(r'("(?:[^"\\]|\\.)*")', program)
    for i in range(0, len(parts), 2):  # even indices are outside string literals
        parts[i] = re.sub(rf"\b{OUTPUT_REL}\b", new_name, parts[i])
    return "".join(parts)
