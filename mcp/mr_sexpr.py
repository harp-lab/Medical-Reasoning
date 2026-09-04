"""Reading a long daemon line without drowning in it.

The daemon's introspection lines are s-expressions, and some are enormous: one
`(pipeline ...)` carries a stratum roster, a version-id table, and one `(rel
NAME (v ORD POS SIZE))` child PER RELATION.  Cutting it at a character count --
which is what slog_server.rkt does to keep the socket reply small -- throws away
the shape along with the bulk, and the shape is the part worth having.  The
third field of `(v ORD POS SIZE)` is the relation's live tuple count, and it
never survives a flat stub.

So shorten by STRUCTURE instead.  Children that fit are printed whole; a child
that does not is shortened in the way that preserves what it is:

  - a run of repeated siblings -- `(strata (s ..) (s ..) (s ..) ...)` -- keeps
    the first few and says how many more there were, so the count survives even
    when the entries do not
  - anything else is cut at a character budget, as before

This is a VIEW.  It exists next to the untouched line in the run's stream file,
so anything elided here is one `less` away, and nothing is inferred or computed
-- every character printed came from the line itself.
"""

import re

# Atoms keep their original text, quotes and all: a rendered node should be
# comparable against the line it came from without a decoding step in between.
_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+')

MORE = "..."


def parse(text):
    """Top-level forms as nested lists of raw atom text, or None if the parens
    do not balance.  A daemon line is one form; anything else falls back."""
    stack = [[]]
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            if len(stack) == 1:
                return None
            top = stack.pop()
            stack[-1].append(top)
        else:
            stack[-1].append(t)
    return stack[0] if len(stack) == 1 else None


def flat(node):
    if isinstance(node, str):
        return node
    return "(" + " ".join(flat(c) for c in node) + ")"


def _head(node):
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return None


def _repeated(node):
    """The shared head of a node's children when they are a homogeneous run --
    `(strata (s ..) (s ..) (s ..))` -> "s".  Three is the threshold: two
    children are cheaper to print than to describe."""
    if not isinstance(node, list) or len(node) < 4:
        return None
    kids = node[1:]
    if not all(isinstance(c, list) for c in kids):
        return None
    heads = {_head(c) for c in kids}
    return kids[0][0] if len(heads) == 1 and None not in heads else None


def _cut(s, budget):
    """A prefix of `s` ending on a TOKEN boundary.

    Cutting mid-token is how a view starts lying: half of
    `"vk-1a0639bd8a1-00000000"` is a different, plausible-looking version key,
    and half of a number is a different number.  Everything this module prints
    should be findable in the line it came from."""
    limit = max(budget - len(MORE) - 2, 8)
    cut = 0
    for m in _TOK.finditer(s):
        if m.end() > limit:
            break
        cut = m.end()
    return s[:cut or limit] + f" {MORE})"


def _shorten(node, budget, keep):
    """One child as at most roughly `budget` characters, shape first."""
    s = flat(node)
    if len(s) <= budget:
        return s
    rep = _repeated(node)
    if rep:
        # Size the kept siblings from what is actually left after the head and
        # the "+N more" tail, and drop them entirely rather than overrun: a
        # child measuring itself against the WHOLE budget made every parent
        # overshoot by a factor of `keep`.
        for n in range(keep, -1, -1):
            tail = f" {MORE} +{len(node) - 1 - n} more ({rep} {MORE}))"
            room = budget - len(node[0]) - 2 - len(tail) - max(n - 1, 0)
            if n == 0:
                # The irreducible form.  If even that overruns, the budget is
                # too small to say anything structural and a plain cut is honest.
                out = f"({node[0]}" + tail
                return out if len(out) <= budget else _cut(s, budget)
            if room // n >= 20:
                shown = [_shorten(c, room // n, keep) for c in node[1:1 + n]]
                return f"({node[0]} " + " ".join(shown) + tail
    return _cut(s, budget)


def render(text, width=96, budget=None, keep=2, cont=None, max_lines=6):
    """Display lines for one daemon line, the first with no indent.

    Short lines come back untouched and unparsed -- most lines are short, and a
    line that already fits should reach the screen as itself.

    `max_lines` caps how many rows one line may occupy: a single `(arms ...)`
    naming fifty choice groups is a legitimate line, and it will bury the
    timeline it sits in.  0 lifts the cap.
    """
    text = text.rstrip("\n")
    if len(text) <= width:
        return [text]
    if text.endswith(f" {MORE})"):
        # Already cut upstream -- slog_server.rkt's 160-char stub closes the
        # paren, so this parses as a well-formed form whose last child is a
        # fragment.  Laying that out as structure would dress up a truncation
        # as a shape the daemon never emitted.
        return [_cut(text, width)]
    forms = parse(text)
    if not forms or len(forms) != 1 or not isinstance(forms[0], list):
        # Not one well-formed s-expression -- an already-stubbed line reaches
        # here.  Fall back to a flat cut rather than pretending a structure
        # that is not there.
        return [_cut(text, width)]

    node = forms[0]
    head = _head(node) or ""
    pad = " " * len(cont) if isinstance(cont, str) else " " * min(len(head) + 2, 14)
    # The continuation indent eats into every line but the first, so the budget
    # a child gets is what is left after it -- otherwise a child sized to the
    # full width overruns as soon as it wraps.
    budget = (budget or width) - len(pad)
    pieces = [_shorten(c, budget, keep) for c in node[1:]]

    rep = _repeated(node)
    lines, cur = [], "(" + head
    for i, p in enumerate(pieces):
        if len(cur) + 1 + len(p) <= width:
            cur += " " + p
            continue
        if max_lines and len(lines) + 2 > max_lines:
            tail = (f"{MORE} +{len(pieces) - i} more"
                    + (f" ({rep} {MORE})" if rep else "") + ")")
            if len(cur) + 1 + len(tail) <= width:
                lines.append(cur + " " + tail)
            else:
                lines.append(cur)
                lines.append(pad + tail)
            return lines
        lines.append(cur)
        cur = pad + p
    lines.append(cur + ")")
    return lines
