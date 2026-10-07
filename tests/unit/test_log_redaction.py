"""The logging layer's redaction (BUG-40): what it removes, and what it keeps."""

import pytest

from app.core.logging import REDACTED, redact_sensitive, redact_text


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        (
            "[parameters: ('alice@example.com', '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA')]",
            "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        ),
        ("DETAIL:  Key (email)=(alice@example.com) already exists.", "alice@example.com"),
        (
            "cookie access_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln here",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln",
        ),
        ("400 Bad Request: token=abcDEF123-_x", "abcDEF123-_x"),
        ('{"password": "hunter2-hunter2"}', "hunter2-hunter2"),
        ("hash " + "a" * 64, "a" * 64),
        ("secret JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"),
        ("recovery A7KM-3PQR-XT29 used", "A7KM-3PQR-XT29"),
    ],
    ids=[
        "sql-params",
        "constraint-detail",
        "jwt",
        "token-query",
        "json-password",
        "sha256",
        "totp-secret",
        "recovery-code",
    ],
)
def test_secrets_and_personal_data_are_removed_from_text(raw: str, secret: str) -> None:
    assert secret not in redact_text(raw)


@pytest.mark.parametrize(
    "hostile",
    [
        "E" * 200_000,
        "a." * 100_000,
        "a@" * 100_000,
        "eyJ" + "a" * 200_000,
        "password=" + "x" * 200_000,
        "0" * 200_000,
        "A-" * 100_000,
    ],
    ids=["letters", "dots", "at-signs", "jwt-prefix", "key-value", "hex", "code-dashes"],
)
def test_redaction_is_linear_on_huge_values(hostile: str) -> None:
    """Regression: an unanchored greedy email pattern backtracked from every
    start position, so a 100 kB provider error took over twenty minutes to log.
    A log line is partly attacker-shaped; redaction must stay O(n)."""
    import time

    started = time.perf_counter()
    redact_text(hostile)
    assert time.perf_counter() - started < 1.0


def test_ordinary_diagnostics_survive() -> None:
    text = (
        "IntegrityError: duplicate key value violates unique constraint "
        "ix_users_email_live req_0123456789abcdef0123456789abcdef"
    )
    assert redact_text(text) == text


def test_sensitive_keys_are_blanked_at_any_depth() -> None:
    event = {
        "event": "login",
        "password": "hunter2",
        "context": {"Token": "abc", "items": [{"secret": "s"}], "user_id": "u-1"},
        "email": "bob@example.com",
    }
    out = redact_sensitive(None, "info", dict(event))
    assert out["password"] == REDACTED
    assert out["context"]["Token"] == REDACTED
    assert out["context"]["items"][0]["secret"] == REDACTED
    assert out["context"]["user_id"] == "u-1"
    assert "bob@example.com" not in str(out)
    assert out["event"] == "login"
