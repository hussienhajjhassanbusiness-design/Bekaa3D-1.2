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


def test_the_ip_hash_pepper_salt_and_key_are_redacted_by_key() -> None:
    """VS-046: whatever these hold, their values never reach a log line."""
    event = {
        "event": "x",
        "ip_hash_salt": "pepper-value",
        "Salt": b"\x01" * 32,
        "pepper": "pepper-value",
        "ip_hash_key": b"\x02" * 32,
        "nested": {"salt": "abc"},
    }
    out = redact_sensitive(None, "info", event)
    assert out["ip_hash_salt"] == out["Salt"] == out["pepper"] == out["ip_hash_key"] == REDACTED
    assert out["nested"] == {"salt": REDACTED}


# --------------------------------------------------------------------------
# VS-028: the contact phone, its hash and the hash key
# --------------------------------------------------------------------------


def test_the_phone_keys_and_the_phone_hash_salt_are_redacted_by_key() -> None:
    event = {
        "event": "x",
        "phone_hash_salt": "salt-value",
        "phone": "+9613123456",
        "contact_phone": "+9613123456",
        "Contact_Phone_Snapshot": "+9613123456",
        "contact_phone_hash": "a" * 64,
    }
    out = redact_sensitive(None, "info", event)
    for key in (
        "phone_hash_salt",
        "phone",
        "contact_phone",
        "Contact_Phone_Snapshot",
        "contact_phone_hash",
    ):
        assert out[key] == REDACTED, key


@pytest.mark.parametrize(
    "raw",
    [
        'new row for relation "orders" violates check constraint: (+9613123456, cash)',
        "DETAIL: Failing row contains (9613123456).",
        "phone=+96171999888;",
    ],
    ids=["e164", "no-plus", "mobile"],
)
def test_a_lebanese_number_inside_text_is_redacted(raw: str) -> None:
    out = redact_text(raw)
    assert "[redacted-phone]" in out
    assert "3123456" not in out and "71999888" not in out


@pytest.mark.parametrize(
    "text",
    [
        "order 961123ab-4e1f-4a2b-9c3d-961123456789 failed",
        "user 01234567-89ab-4cde-8f01-9613123456ff",
        "order B3D-9613ABCD placed",
        "amount_cents=96131234567890",
    ],
    ids=["uuid-group", "uuid-tail", "order-number", "long-digit-run"],
)
def test_uuids_order_numbers_and_long_digit_runs_are_not_phones(text: str) -> None:
    assert redact_text(text) == text


def test_phone_redaction_is_linear_on_huge_digit_runs() -> None:
    import time

    started = time.perf_counter()
    redact_text("961" * 100_000)
    redact_text("+961" + "1" * 200_000)
    assert time.perf_counter() - started < 1.0
