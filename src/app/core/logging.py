import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import get_settings

REDACTED = "[redacted]"

# Keys whose values are never logged, whatever they contain. Matched
# case-insensitively against event-dict keys.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "password_hash",
        "token",
        "raw_token",
        "secret",
        "totp_secret",
        "otpauth_uri",
        "recovery_code",
        "recovery_codes",
        "access_token",
        "refresh_token",
        "csrf_token",
        "authorization",
        "cookie",
        "set-cookie",
        "verification_url",
        "reset_url",
        # VS-046 (ADR-028): the IP-hash pepper, the database salt and the derived key.
        "ip_hash_salt",
        "salt",
        "pepper",
        "ip_hash_key",
        # VS-023: webhook signing material and raw provider bodies.
        "mock_webhook_secret",
        "webhook_secret",
        "signature",
        "x-mock-signature",
        "webhook_body",
    }
)

# Values that are secret or personal wherever they appear inside a string -
# including the text of an exception and its traceback, which is where a
# database error carries SQL parameters and constraint details.
#
# Every pattern must run in linear time: log values are partly attacker-shaped
# (a provider error, an exception message) and can be very long. An unanchored
# greedy run such as `[\w.+-]+@` backtracks from every start position when no
# `@` follows - quadratic, and a 100 kB value took over twenty minutes. So each
# unbounded run is possessive (`++`, never gives characters back) and may only
# start where a run starts (the negative lookbehind), which together keep every
# pattern O(n).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\$argon2(?:id|i|d)\$[^\s'\",)\]]++"), "[redacted-hash]"),
    (re.compile(r"(?<![\w-])eyJ[\w-]++\.[\w-]++\.[\w-]*+"), "[redacted-jwt]"),
    (
        re.compile(
            r"(?i)(?<![\w])(password|new_password|current_password|token|secret|recovery_code"
            r"|csrf_token|access_token|refresh_token)(['\"]?\s*+[:=]\s*+['\"]?)"
            r"([^'\"&\s,;)}\]]++)"
        ),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"(?<![\w.+-])[\w.+-]++@[\w-]++(?:\.[\w-]++)++"), "[redacted-email]"),
    (re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])"), "[redacted-digest]"),
    (re.compile(r"(?<![A-Z2-7])[A-Z2-7]{32}(?![A-Z2-7])"), "[redacted-secret]"),
    (
        re.compile(r"(?<![A-Z0-9])[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}(?![A-Z0-9])"),
        "[redacted-code]",
    ),
)


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: REDACTED if str(key).lower() in _SENSITIVE_KEYS else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(_redact_value(item) for item in value)
    return value


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: the last line of defence before anything is rendered.

    Runs in the formatter, after tracebacks have been turned into text, so it
    covers every record the process emits - the application's own events, and
    foreign stdlib records (SQLAlchemy, uvicorn) alike. Call sites should still
    never log a secret; this exists because a database error's message carries
    SQL parameters and constraint details that no call site chose to log."""
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


_ADMIN_PREFIX = "/api/v1/admin"


class AdminQueryStringFilter(logging.Filter):
    """Drop the query string from an access-log line for any admin path (BUG-39).

    uvicorn logs every request on `uvicorn.access` with the path *and* query
    string, through its own handler and formatter, so `redact_sensitive` never
    sees the line - and the `?search=` of the admin user list is an email
    address. api-endpoints.md 533 requires that PII access be "redacted from
    logs", and an admin query string is the place PII gets typed: every
    `/api/v1/admin` path loses its query string, not only `/admin/users`.

    The record is rewritten, never dropped, so the request still shows up.
    `args` is uvicorn's `(client, method, path_with_query, http_version,
    status)`; a record of any other shape is left alone. uvicorn builds the
    path with `urllib.parse.quote(scope["path"])`, which escapes `?`, so the
    first `?` is always the start of the query string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path, separator, _query = args[2].partition("?")
            if separator and (path == _ADMIN_PREFIX or path.startswith(_ADMIN_PREFIX + "/")):
                record.args = (args[0], args[1], path, args[3], args[4])
        return True


def install_access_log_filter() -> None:
    """Attach `AdminQueryStringFilter` to `uvicorn.access`, once.

    On the logger rather than a handler: uvicorn configures that logger's
    handlers itself, before the app starts, and a logger filter runs ahead of
    whichever handlers it ends up with."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AdminQueryStringFilter) for f in access.filters):
        access.addFilter(AdminQueryStringFilter())


def configure_logging() -> None:
    settings = get_settings()
    install_access_log_filter()

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # Tracebacks become text *before* redaction, so a secret inside an
            # exception message is scrubbed like any other string.
            structlog.processors.format_exc_info,
            redact_sensitive,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)
