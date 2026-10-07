"""BUG-39: no admin query string - an email search above all - reaches the access log.

uvicorn logs every request on `uvicorn.access` with the path *and* query string,
through its own handler, so the structlog redactor never sees the line. The
filter rewrites the record itself, before any handler formats it.
"""

import logging

import pytest

from app.core.logging import AdminQueryStringFilter, install_access_log_filter

# Exactly how uvicorn's h11/httptools protocols log a request.
_ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'


def _access_record(full_path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=_ACCESS_FORMAT,
        args=("127.0.0.1:50000", "GET", full_path, "1.1", 200),
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("full_path", "logged"),
    [
        ("/api/v1/admin/users?search=victim.person%40example.com", "/api/v1/admin/users"),
        ("/api/v1/admin/users?search=victim.person@example.com", "/api/v1/admin/users"),
        ("/api/v1/admin/audit-logs?actor_user_id=x&cursor=y", "/api/v1/admin/audit-logs"),
        ("/api/v1/admin?x=1", "/api/v1/admin"),
        ("/api/v1/admin/users", "/api/v1/admin/users"),
    ],
)
def test_an_admin_query_string_is_dropped(full_path: str, logged: str) -> None:
    record = _access_record(full_path)
    assert AdminQueryStringFilter().filter(record) is True
    message = record.getMessage()
    assert message == f'127.0.0.1:50000 - "GET {logged} HTTP/1.1" 200'
    assert "victim" not in message


@pytest.mark.parametrize(
    "full_path",
    [
        "/api/v1/me/notifications?cursor=abc",
        "/api/v1/categories?limit=5",
        # Not under the admin router: the boundary treats these as ordinary paths.
        "/api/v1/admin-x?q=1",
        "/api/v1/administrators?q=1",
    ],
)
def test_other_query_strings_are_kept(full_path: str) -> None:
    record = _access_record(full_path)
    assert AdminQueryStringFilter().filter(record) is True
    assert full_path in record.getMessage()


def test_a_record_of_another_shape_is_left_alone() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something else: %s",
        args=("/api/v1/admin/users?search=x",),
        exc_info=None,
    )
    assert AdminQueryStringFilter().filter(record) is True
    assert record.getMessage() == "something else: /api/v1/admin/users?search=x"


def test_installing_attaches_one_filter_to_the_access_logger() -> None:
    access = logging.getLogger("uvicorn.access")
    before = list(access.filters)
    try:
        install_access_log_filter()
        install_access_log_filter()
        added = [f for f in access.filters if isinstance(f, AdminQueryStringFilter)]
        assert len(added) == 1
    finally:
        access.filters = before
