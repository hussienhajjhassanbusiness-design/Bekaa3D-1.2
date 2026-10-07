"""The approved V1 numeric contracts, pinned to literals.

The integration tests drive these endpoints using the production constants,
which proves the limiter and the cap are genuinely wired up. What that cannot
detect is *policy drift*: if someone changed `PUBLIC_RATE_LIMIT` to 60, those
tests would happily exercise 60 requests and still pass.

These assertions are the other half. They carry the approved numbers as
literals, so changing a policy requires changing this file too - which is
exactly the reviewed, deliberate step an approved V1 decision deserves.

None of these numbers comes from the SRS. `api-endpoints.md` says "hard-limited
reference list" and lists `429` without giving a policy; the values below are
V1 product/operational decisions recorded in docs/reference-data.md.
"""

from app.catalog.api.reference_data import (
    PUBLIC_LIST_LIMIT,
    PUBLIC_RATE_LIMIT,
    PUBLIC_RATE_WINDOW_SECONDS,
)


def test_the_public_rate_limit_is_600_per_hour() -> None:
    """Same starting policy as VS-007's public settings endpoint: generous
    enough that no human browsing reaches it, tight enough to bite a scraper."""
    assert PUBLIC_RATE_LIMIT == 600
    assert PUBLIC_RATE_WINDOW_SECONDS == 3600


def test_the_public_reference_hard_cap_is_100() -> None:
    """The bound on `GET /categories|/materials|/colours`. These are facet lists
    rather than paginated collections, so the cap is the whole contract - there
    is no cursor to fetch a second page with."""
    assert PUBLIC_LIST_LIMIT == 100
