"""Characters no text from a client may carry (BUG-03).

PostgreSQL TEXT and JSONB cannot store NUL at all: a NUL that reached the
driver raised deep inside asyncpg and the request answered 500. The other C0
controls and DEL *can* be stored, but no legitimate name, key, token, cursor or
search term contains them - they only ever arrive from a broken client or a
hostile one, and they make stored text render or log misleadingly.

So every text value a client sends is refused - 422, never stored, never
queried - if it contains one. Free text that may legitimately span lines (a
setting such as the pickup hours) keeps tab, line feed and carriage return.

Pure: no framework imports, so the domain layer may use it too.
"""

import re

# C0 controls (U+0000-U+001F) and DEL (U+007F).
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# The same, minus tab, line feed and carriage return.
_CONTROL_EXCEPT_LINE_BREAKS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

CONTROL_CHARACTER_MESSAGE = "must not contain control characters"


def has_control_characters(value: str, *, allow_line_breaks: bool = False) -> bool:
    pattern = _CONTROL_EXCEPT_LINE_BREAKS if allow_line_breaks else _CONTROL
    return pattern.search(value) is not None


def reject_control_characters(value: str) -> str:
    """A Pydantic `AfterValidator`: the value unchanged, or `ValueError`."""
    if has_control_characters(value):
        raise ValueError(CONTROL_CHARACTER_MESSAGE)
    return value


def json_contains_nul(value: object) -> bool:
    """Whether any string - key or value - anywhere in a JSON-like structure
    contains NUL, which PostgreSQL JSONB rejects even escaped as `\\u0000`.

    Iterative, not recursive, so a pathologically deep structure cannot turn
    the check itself into a RecursionError."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if "\x00" in item:
                return True
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return False
