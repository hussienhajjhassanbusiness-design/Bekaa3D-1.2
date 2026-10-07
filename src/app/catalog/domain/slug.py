"""Slug normalisation and validation for catalogue reference data.

Pure domain: no framework, no database.

The project had no slug code before this slice and `database-design.md` gives
`slug` only as `TEXT` with a partial unique index - no pattern, no length. The
rules below are therefore a **V1 decision made here**, not an existing
convention being followed, and they are documented as such in
`docs/reference-data.md`.
"""

import re

from app.catalog.domain.exceptions import InvalidSlugError

# 200 characters, matching the longest existing string bound in the project
# (`pickup_hours` in the settings registry). The column itself is TEXT and
# imposes no limit; this is input hygiene at the edge, so a pathological slug
# cannot end up in a URL or an index.
MAX_SLUG_LENGTH = 200

# Lowercase alphanumerics in hyphen-separated groups. No leading, trailing or
# repeated hyphens, which is what keeps one logical slug from having several
# spellings that all look the same in a URL bar.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalise_slug(raw: str) -> str:
    """Trim and lowercase, then validate. Returns the canonical form.

    Deliberately **not** a slugifier: it will not turn "Desk Lamps" into
    "desk-lamps". `CategoryCreate` takes an explicit `slug` field alongside
    `name`, so the administrator chooses the URL; silently rewriting their input
    would mean the slug they were shown is not the slug that was stored. What it
    does normalise is case and surrounding whitespace, because `"Lamps "` and
    `"lamps"` are the same slug and storing both would defeat the unique index.
    """
    if not isinstance(raw, str):
        raise InvalidSlugError(str(raw), "slug must be a string")

    candidate = raw.strip().lower()

    if not candidate:
        raise InvalidSlugError(raw, "slug must not be empty")
    if len(candidate) > MAX_SLUG_LENGTH:
        raise InvalidSlugError(raw, f"slug must be at most {MAX_SLUG_LENGTH} characters")
    if not _SLUG_PATTERN.match(candidate):
        raise InvalidSlugError(
            raw,
            "slug may contain only lowercase letters, digits and single hyphens between them",
        )
    return candidate
