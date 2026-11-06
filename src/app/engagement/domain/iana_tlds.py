"""IANA's root-zone TLDs (ADR-044 amendment). `iana_tlds.txt` is a verbatim copy of
https://data.iana.org/TLD/tlds-alpha-by-domain.txt: refresh it by replacing the file."""

import unicodedata
from importlib.resources import files
from typing import Final

_LINES: Final = files("app.engagement.domain").joinpath("iana_tlds.txt").read_text("ascii")


def _fold(tld: str) -> str:
    return unicodedata.normalize("NFKC", tld).casefold()


def _load(lines: list[str]) -> frozenset[str]:
    """Every ending folded as review text is, and each IDN in Unicode too: NFKC keeps
    `شبكة` as typed, so its `xn--` form alone would never match."""
    ascii_tlds = [_fold(line.strip()) for line in lines if line.strip() and line[0] != "#"]
    idns = [_fold(t[4:].encode("ascii").decode("punycode")) for t in ascii_tlds if t[:4] == "xn--"]
    return frozenset(ascii_tlds + idns)


IANA_TLDS_VERSION: Final = _LINES.split(",", 1)[0].removeprefix("# Version ")
IANA_TLDS: Final = _load(_LINES.splitlines())
