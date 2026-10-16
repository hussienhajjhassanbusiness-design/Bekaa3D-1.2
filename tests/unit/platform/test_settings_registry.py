"""The setting registry: what exists, and what each key will accept.

These are pure domain tests with no database. The registry is the only thing
standing between an administrator and an out-of-range business parameter, and
every rule it enforces is checked here rather than inferred from an endpoint
test - an API test that posts one bad value proves that *a* check exists, not
that the right one does.
"""

import pytest

from app.platform.domain.enums import SettingType
from app.platform.domain.exceptions import InvalidSettingValueError, SettingNotFoundError
from app.platform.domain.settings_registry import (
    ALL_KEYS,
    PUBLIC_KEYS,
    REGISTRY,
    definition_for,
    validate_value,
)

# The twelve SRS 15.4 requires plus VS-046's two retention periods, written out
# rather than derived from the registry: a test that builds its expectation from
# the thing under test would pass just as happily if a key were deleted.
REQUIRED_KEYS = (
    "accepting_orders",
    "offer_response_window",
    "offer_checkout_window",
    "offer_rejection_cooldown",
    "minimum_offer_percentage",
    "checkout_hold_period",
    "unverified_account_purge_period",
    "daily_download_cap",
    "free_shipping_threshold",
    "pickup_address",
    "pickup_hours",
    "whatsapp_number",
    "security_token_retention_period",
    "session_retention_period",
)


# --------------------------------------------------------------------------
# Shape of the registry itself
# --------------------------------------------------------------------------


def test_the_registry_holds_exactly_the_required_settings() -> None:
    assert set(REGISTRY) == set(REQUIRED_KEYS)
    assert len(ALL_KEYS) == len(REQUIRED_KEYS)


def test_the_public_allowlist_is_exactly_the_five_documented_keys() -> None:
    """api-endpoints.md lists these five under PublicSettingsRead.

    Hard-coded rather than filtered out of the registry, because the whole
    security property is that this set does not drift: a test that recomputed it
    from `is_public` would follow the mistake it is supposed to catch.
    """
    assert PUBLIC_KEYS == (
        "accepting_orders",
        "free_shipping_threshold",
        "pickup_address",
        "pickup_hours",
        "whatsapp_number",
    )


def test_no_internal_setting_is_marked_public() -> None:
    """Stated from the other direction, so the assertion still bites if someone
    adds a key *and* adds it to the list above."""
    internal = {
        "offer_response_window",
        "offer_checkout_window",
        "offer_rejection_cooldown",
        "minimum_offer_percentage",
        "checkout_hold_period",
        "unverified_account_purge_period",
        "daily_download_cap",
        "security_token_retention_period",
        "session_retention_period",
    }
    for key in internal:
        assert REGISTRY[key].is_public is False, f"{key} must not be public"
        assert key not in PUBLIC_KEYS


def test_every_default_satisfies_its_own_rules() -> None:
    """The seed would otherwise ship values the API would refuse to accept -
    a state an administrator could never restore after changing one."""
    for key, definition in REGISTRY.items():
        assert validate_value(key, definition.default) == definition.default, key


def test_an_unregistered_key_is_not_found() -> None:
    with pytest.raises(SettingNotFoundError):
        definition_for("totally_made_up")
    with pytest.raises(SettingNotFoundError):
        validate_value("totally_made_up", 1)


# --------------------------------------------------------------------------
# Booleans
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_setting_accepts_booleans(value: bool) -> None:
    assert validate_value("accepting_orders", value) is value


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(1, id="int-1"),
        pytest.param(0, id="int-0"),
        pytest.param("true", id="string"),
        pytest.param(None, id="null"),
    ],
)
def test_a_boolean_setting_rejects_everything_else(value: object) -> None:
    """`1` is not `true`. Accepting it would put two spellings of the same
    state in the table, and `None` is rejected because this setting is not
    nullable - the shop is either open or closed."""
    with pytest.raises(InvalidSettingValueError):
        validate_value("accepting_orders", value)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Integers and durations
# --------------------------------------------------------------------------


def test_an_integer_setting_accepts_a_whole_number_in_range() -> None:
    assert validate_value("minimum_offer_percentage", 70) == 70
    assert validate_value("minimum_offer_percentage", 0) == 0
    assert validate_value("minimum_offer_percentage", 100) == 100


@pytest.mark.parametrize(
    ("value", "why"),
    [
        pytest.param(-1, "below minimum", id="below-min"),
        pytest.param(101, "above maximum", id="above-max"),
        pytest.param(70.5, "fractional", id="float"),
        pytest.param("70", "numeric string", id="numeric-string"),
        pytest.param(None, "null", id="null"),
    ],
)
def test_an_integer_setting_rejects_out_of_range_and_wrong_types(value: object, why: str) -> None:
    with pytest.raises(InvalidSettingValueError):
        validate_value("minimum_offer_percentage", value)  # type: ignore[arg-type]


def test_true_is_not_an_integer() -> None:
    """The trap this codebase has hit before. `isinstance(True, int)` is True in
    Python, so a naive check reads `true` as 1 - here it would silently set the
    offer floor to 1% of list price."""
    with pytest.raises(InvalidSettingValueError):
        validate_value("minimum_offer_percentage", True)
    with pytest.raises(InvalidSettingValueError):
        validate_value("daily_download_cap", True)
    with pytest.raises(InvalidSettingValueError):
        validate_value("offer_response_window", True)


def test_durations_are_whole_seconds_within_their_window() -> None:
    assert validate_value("offer_response_window", 3_600) == 3_600
    assert validate_value("offer_response_window", 604_800) == 604_800
    with pytest.raises(InvalidSettingValueError):
        validate_value("offer_response_window", 3_599)
    with pytest.raises(InvalidSettingValueError):
        validate_value("offer_response_window", 604_801)


def test_the_rejection_cooldown_may_be_zero() -> None:
    """Zero means "no cooldown", which is a legitimate operating choice - so
    unlike the other durations this one is not bounded away from zero."""
    assert validate_value("offer_rejection_cooldown", 0) == 0
    with pytest.raises(InvalidSettingValueError):
        validate_value("offer_rejection_cooldown", -1)


def test_the_purge_period_keeps_the_previous_hardcoded_behaviour() -> None:
    """30 days, exactly what the job used from a source-code constant before
    VS-007, so moving the control into the database changed nothing."""
    assert REGISTRY["unverified_account_purge_period"].default == 2_592_000


@pytest.mark.parametrize(
    ("key", "default"),
    [("security_token_retention_period", 604_800), ("session_retention_period", 2_592_000)],
)
def test_the_retention_periods_are_one_to_ninety_days(key: str, default: int) -> None:
    """VS-046 owner decision: 7 d tokens, 30 d sessions, editable within 1-90 d."""
    assert REGISTRY[key].default == default
    assert validate_value(key, 86_400) == 86_400
    assert validate_value(key, 7_776_000) == 7_776_000
    with pytest.raises(InvalidSettingValueError):
        validate_value(key, 86_399)
    with pytest.raises(InvalidSettingValueError):
        validate_value(key, 7_776_001)


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


def test_money_accepts_the_standard_shape() -> None:
    value = {"amount_cents": 5_000, "currency": "USD"}
    assert validate_value("free_shipping_threshold", value) == value


def test_money_may_be_null_because_free_shipping_is_optional() -> None:
    """BR-076 calls the threshold optional, so "off" has to be representable.
    JSON null is that."""
    assert validate_value("free_shipping_threshold", None) is None


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"amount_cents": 1_000}, id="missing-currency"),
        pytest.param({"amount_cents": 1_000, "currency": "LBP"}, id="wrong-currency"),
        pytest.param({"amount_cents": -1, "currency": "USD"}, id="negative"),
        pytest.param({"amount_cents": 1_000_001, "currency": "USD"}, id="above-max"),
        pytest.param({"amount_cents": 19.99, "currency": "USD"}, id="float-cents"),
        pytest.param({"amount_cents": 1_000, "currency": "USD", "extra": 1}, id="extra-key"),
        pytest.param(1_000, id="bare-number"),
    ],
)
def test_money_rejects_malformed_amounts(value: object) -> None:
    with pytest.raises(InvalidSettingValueError):
        validate_value("free_shipping_threshold", value)  # type: ignore[arg-type]


def test_a_money_value_reports_every_problem_at_once() -> None:
    """An admin fixing a value should see all of it, not discover the second
    fault only after fixing the first."""
    with pytest.raises(InvalidSettingValueError) as raised:
        validate_value("free_shipping_threshold", {"amount_cents": -5, "currency": "EUR"})
    assert len(raised.value.reasons) == 2


# --------------------------------------------------------------------------
# Strings
# --------------------------------------------------------------------------


def test_a_string_setting_is_stored_trimmed() -> None:
    """Normalisation, not just validation: otherwise `" Beirut "` and
    `"Beirut"` are two different stored values of one setting."""
    assert validate_value("pickup_address", "  Workshop, Zahle  ") == "Workshop, Zahle"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace-only"),
        pytest.param(123, id="not-a-string"),
    ],
)
def test_a_string_setting_rejects_empty_and_non_strings(value: object) -> None:
    with pytest.raises(InvalidSettingValueError):
        validate_value("pickup_address", value)  # type: ignore[arg-type]


def test_string_length_limits_are_enforced_after_trimming() -> None:
    assert validate_value("pickup_hours", "x" * 200) == "x" * 200
    with pytest.raises(InvalidSettingValueError):
        validate_value("pickup_hours", "x" * 201)
    with pytest.raises(InvalidSettingValueError):
        validate_value("pickup_address", "x" * 501)


def test_public_strings_may_be_null_while_the_client_values_are_awaited() -> None:
    for key in ("pickup_address", "pickup_hours", "whatsapp_number"):
        assert validate_value(key, None) is None


# --------------------------------------------------------------------------
# E.164
# --------------------------------------------------------------------------


@pytest.mark.parametrize("number", ["+96170123456", "+15551234567", "+9"])
def test_the_whatsapp_number_accepts_canonical_e164(number: str) -> None:
    assert validate_value("whatsapp_number", number) == number


@pytest.mark.parametrize(
    "number",
    [
        pytest.param("96170123456", id="no-plus"),
        pytest.param("+0170123456", id="leading-zero-country-code"),
        pytest.param("+961 70 123 456", id="spaces"),
        pytest.param("+961-70-123456", id="dashes"),
        pytest.param("+9617012345678901", id="too-many-digits"),
        pytest.param("+", id="plus-only"),
        pytest.param("+96170abc456", id="letters"),
    ],
)
def test_the_whatsapp_number_rejects_non_canonical_forms(number: str) -> None:
    """Separators are presentation. Storing them would mean two spellings of one
    number and a `wa.me` link that works for one of them and not the other."""
    with pytest.raises(InvalidSettingValueError):
        validate_value("whatsapp_number", number)


def test_a_whatsapp_number_is_trimmed_before_it_is_checked() -> None:
    assert validate_value("whatsapp_number", "  +96170123456  ") == "+96170123456"


# --------------------------------------------------------------------------
# Declared types
# --------------------------------------------------------------------------


def test_each_setting_declares_the_type_its_consumers_expect() -> None:
    expected = {
        "accepting_orders": SettingType.BOOLEAN,
        "offer_response_window": SettingType.DURATION,
        "offer_checkout_window": SettingType.DURATION,
        "offer_rejection_cooldown": SettingType.DURATION,
        "minimum_offer_percentage": SettingType.INTEGER,
        "checkout_hold_period": SettingType.DURATION,
        "unverified_account_purge_period": SettingType.DURATION,
        "daily_download_cap": SettingType.INTEGER,
        "free_shipping_threshold": SettingType.MONEY,
        "pickup_address": SettingType.STRING,
        "pickup_hours": SettingType.STRING,
        "whatsapp_number": SettingType.STRING,
        "security_token_retention_period": SettingType.DURATION,
        "session_retention_period": SettingType.DURATION,
    }
    assert {key: definition.type for key, definition in REGISTRY.items()} == expected
