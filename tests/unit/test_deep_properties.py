"""Property-based tests (Hypothesis) for the pure validators and parsers.

`database=None` keeps Hypothesis from writing a `.hypothesis/` directory into
the repository, and `derandomize=True` makes every run - local or CI - explore
the same inputs. Properties expected to fail pin their known counterexample
with `@example`, so the xfail does not depend on the search finding it.
"""

import contextlib
import json
import string
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import jwt
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from pydantic import EmailStr, TypeAdapter

from app.catalog.api import reference_data
from app.core.config import get_settings
from app.core.security import csrf_token_for_session, hash_ip, verify_csrf_token
from app.engagement.api import notifications
from app.engagement.domain.exceptions import InvalidNotificationPayloadError
from app.engagement.domain.payload import MAX_PAYLOAD_BYTES, validate_payload
from app.identity.api import admin_users
from app.identity.application.security.session_tokens import (
    decode_access_token,
    decode_refresh_token,
)
from app.identity.application.security.totp import verify_code_step
from app.identity.application.services.login_throttle import MAX_DELAY_SECONDS, _delay_for
from app.identity.domain.exceptions import InvalidSessionError
from app.identity.domain.recovery_codes import _ALPHABET, generate_code, normalize_code
from app.platform.api import settings as settings_api
from app.platform.domain.exceptions import InvalidSettingValueError
from app.platform.domain.settings_registry import REGISTRY, validate_value

PROFILE = settings(
    max_examples=300,
    deadline=None,
    database=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)

_json_scalars = st.none() | st.booleans() | st.integers() | st.text(max_size=20)
_json = st.recursive(
    _json_scalars,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=20,
)


# --------------------------------------------------------------------------
# Token decoding
# --------------------------------------------------------------------------


@PROFILE
@given(st.text())
def test_arbitrary_text_never_crashes_the_token_decoders(raw: str) -> None:
    for decode in (decode_access_token, decode_refresh_token):
        with contextlib.suppress(InvalidSessionError):
            decode(raw)


@PROFILE
@given(
    st.fixed_dictionaries(
        {"typ": st.sampled_from(["access", "refresh"])},
        optional={
            "sub": _json,
            "sid": _json,
            "role": _json,
            "ver": _json,
            "mfa": _json,
            "auth_epoch": _json,
            "tv": _json,
        },
    )
)
@example({"typ": "access", "sub": 1, "sid": str(uuid.uuid4()), "role": "customer", "ver": True})
def test_signed_but_malformed_claims_only_ever_raise_invalid_session(
    claims: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {**claims, "iat": now, "exp": now + timedelta(minutes=5)},
        get_settings().jwt_signing_key,
        algorithm="HS256",
    )
    decode = decode_access_token if claims["typ"] == "access" else decode_refresh_token
    with contextlib.suppress(InvalidSessionError):
        decode(token)


# --------------------------------------------------------------------------
# Cursors
# --------------------------------------------------------------------------

_TIME_CURSORS = [admin_users._parse_cursor, notifications._parse_cursor]


@PROFILE
@given(st.text(max_size=300))
def test_arbitrary_cursor_text_is_parsed_or_refused_with_value_error(raw: str) -> None:
    for parse in (*_TIME_CURSORS, reference_data._parse_cursor, settings_api._validate_cursor):
        with contextlib.suppress(ValueError):
            parse(raw)


@PROFILE
@given(
    st.datetimes(
        min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
    ),
    st.uuids(),
)
def test_time_cursors_round_trip(moment: datetime, identifier: uuid.UUID) -> None:
    for module in (admin_users, notifications):
        assert module._parse_cursor(module._encode_cursor(moment, identifier)) == (
            moment,
            identifier,
        )


@PROFILE
@given(st.text(min_size=1, max_size=40), st.uuids())
def test_name_cursors_round_trip(name: str, identifier: uuid.UUID) -> None:
    assert reference_data._parse_cursor(reference_data._encode_cursor(name, identifier)) == (
        name,
        identifier,
    )


@PROFILE
@given(
    st.datetimes(
        timezones=st.builds(lambda m: timezone(timedelta(minutes=m)), st.integers(-839, 839))
    ),
    st.uuids(),
)
@example(datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14))), uuid.UUID(int=0))
def test_every_accepted_cursor_time_is_representable_in_utc(
    moment: datetime, identifier: uuid.UUID
) -> None:
    import base64

    raw = base64.urlsafe_b64encode(f"{moment.isoformat()}|{identifier}".encode()).decode()
    for parse in _TIME_CURSORS:
        try:
            parsed, _ = parse(raw)  # type: ignore[misc]
        except ValueError:
            continue
        parsed.astimezone(UTC)


# --------------------------------------------------------------------------
# Recovery codes
# --------------------------------------------------------------------------


@PROFILE
@given(st.text())
def test_normalisation_is_idempotent_and_stays_in_the_alphabet(raw: str) -> None:
    once = normalize_code(raw)
    assert normalize_code(once) == once
    assert set(once) <= set(_ALPHABET)


@PROFILE
@given(st.randoms(use_true_random=False), st.sampled_from(["", " ", "-", "  "]))
def test_a_code_survives_any_reasonable_retyping(rng: Any, separator: str) -> None:
    code = generate_code()
    retyped = separator.join(code.replace("-", "")).lower() if rng.random() < 0.5 else code.lower()
    assert normalize_code(retyped) == normalize_code(code)
    assert len(normalize_code(code)) == 12


# --------------------------------------------------------------------------
# Settings validation
# --------------------------------------------------------------------------

_NUMERIC = [k for k, d in REGISTRY.items() if d.type.value in ("integer", "duration")]
_STRINGS = [k for k, d in REGISTRY.items() if d.type.value == "string"]


def _accepted(key: str, value: Any) -> tuple[bool, Any]:
    try:
        return True, validate_value(key, value)
    except InvalidSettingValueError:
        return False, None


@PROFILE
@given(st.sampled_from(_NUMERIC), st.integers(min_value=-(10**12), max_value=10**12))
def test_a_numeric_setting_accepts_exactly_its_range(key: str, number: int) -> None:
    definition = REGISTRY[key]
    ok, _ = _accepted(key, number)
    assert ok is (definition.minimum <= number <= definition.maximum)  # type: ignore[operator]


@PROFILE
@given(
    st.sampled_from(_NUMERIC),
    st.booleans()
    | st.floats(allow_nan=True)
    | st.text(max_size=5)
    | st.lists(st.integers(), max_size=2),
)
def test_a_numeric_setting_never_accepts_a_non_integer(key: str, value: Any) -> None:
    assert _accepted(key, value) == (False, None)


@PROFILE
@given(st.sampled_from(_STRINGS), st.text(max_size=600))
def test_accepted_strings_are_trimmed_bounded_and_idempotent(key: str, value: str) -> None:
    ok, stored = _accepted(key, value)
    if ok and stored is not None:
        assert stored == stored.strip() == value.strip()
        assert len(stored) <= REGISTRY[key].max_length  # type: ignore[operator]
        assert validate_value(key, stored) == stored


@PROFILE
@given(st.sampled_from(["pickup_address", "pickup_hours"]), st.text(max_size=50))
@example("pickup_hours", "Mon\x00Fri")
def test_no_accepted_string_contains_nul(key: str, value: str) -> None:
    ok, stored = _accepted(key, value)
    if ok and stored is not None:
        assert "\x00" not in stored


@PROFILE
@given(st.text(alphabet=string.digits + "٠١٢۱１", min_size=1, max_size=14))
@example("١٢٣")
def test_every_accepted_whatsapp_number_is_ascii(digits: str) -> None:
    ok, stored = _accepted("whatsapp_number", "+9" + digits)
    if ok:
        assert stored.isascii()


@PROFILE
@given(st.integers(-(10**9), 10**9), st.sampled_from(["USD", "usd", "EUR", ""]), st.booleans())
def test_money_is_accepted_only_as_in_range_usd_cents(
    cents: int, currency: str, extra: bool
) -> None:
    value: dict[str, Any] = {"amount_cents": cents, "currency": currency}
    if extra:
        value["note"] = "x"
    ok, _ = _accepted("free_shipping_threshold", value)
    assert ok is (0 <= cents <= 1_000_000 and currency == "USD" and not extra)


# --------------------------------------------------------------------------
# Notification payloads
# --------------------------------------------------------------------------


@PROFILE
@given(st.dictionaries(st.text(max_size=10), _json, max_size=6), st.text(min_size=1, max_size=20))
def test_accepted_payloads_are_bounded_json_and_rejections_are_typed(
    extra: dict[str, Any], event: str
) -> None:
    payload = {**extra, "event": event}
    try:
        accepted = validate_payload(payload)
    except InvalidNotificationPayloadError:
        return
    encoded = json.dumps(accepted, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    assert len(encoded.encode("utf-8")) <= MAX_PAYLOAD_BYTES
    assert accepted["event"].strip()


@PROFILE
@given(st.text(max_size=20))
@example("a\x00b")
def test_no_accepted_payload_contains_nul(text_value: str) -> None:
    try:
        accepted = validate_payload({"event": "x", "value": text_value})
    except InvalidNotificationPayloadError:
        return
    # The raw value, not json.dumps(): JSON escapes NUL as \u0000, which would
    # hide it - but JSONB rejects the escaped form just the same.
    assert "\x00" not in accepted["value"]


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------


@PROFILE
@given(st.emails())
def test_email_normalisation_is_idempotent(raw: str) -> None:
    adapter = TypeAdapter(EmailStr)
    try:
        once = adapter.validate_python(raw)
    except ValueError:
        return
    assert adapter.validate_python(once) == once


@PROFILE
@given(st.ip_addresses().map(str))
def test_ip_hashes_are_deterministic_opaque_and_fixed_width(ip: str) -> None:
    digest = hash_ip(ip)
    assert digest == hash_ip(ip)
    assert len(digest) == 64 and ip not in digest


@PROFILE
@given(st.uuids(), st.text(max_size=80))
@example(uuid.UUID(int=1), "é")
def test_only_the_exact_csrf_token_verifies(session_id: uuid.UUID, presented: str) -> None:
    real = csrf_token_for_session(session_id)
    assert verify_csrf_token(session_id=session_id, presented=presented) is (presented == real)


@PROFILE
@given(st.text(max_size=20))
def test_the_totp_verifier_never_raises_on_hostile_input(code: str) -> None:
    verify_code_step(secret="JBSWY3DPEHPK3PXP", code=code, now=datetime.now(UTC))


@PROFILE
@given(st.integers(min_value=1, max_value=1000))
def test_the_throttle_delay_curve(attempt: int) -> None:
    delay = _delay_for(attempt)
    assert delay == 0 if attempt <= 3 else 0 < delay <= MAX_DELAY_SECONDS
    assert _delay_for(attempt + 1) >= delay
