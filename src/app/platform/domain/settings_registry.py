"""The setting key registry: what exists, what type it is, and what is allowed.

Two sources of truth would be a bug, so it is worth being precise about which
one this is. The **database holds the values**; this module holds everything
else - which keys exist, their declared type, their limits, their unit, and
whether they may be read by the public. A setting the registry does not declare
cannot be read, written, or created through the API, whatever rows happen to be
in the table (api-endpoints.md:632, "Clients cannot create arbitrary setting
keys in V1").

Putting the rules here rather than in the database is what BR-133 asks for in
reverse: the *values* must be operationally changeable without a deployment,
but the *rules* about them are logic, and logic belongs in the domain layer
under review. Widening a range is a code change with a test; changing a value
is a `PATCH`.

The numbers below are V1 product decisions. The SRS deliberately specifies none
of them - it says each is "configurable" and stops there - so they were taken
as explicit decisions rather than inferred, and the defaults are seeded by
migration so a fresh deployment is immediately operable.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Final, TypeGuard

from app.core.text import has_control_characters, json_contains_nul
from app.platform.domain.enums import SettingType
from app.platform.domain.exceptions import InvalidSettingValueError, SettingNotFoundError

# Everything a setting's value may legally be once validated. JSON `null` is
# Python `None`, and is a *value*, not an absence - see SettingDefinition.nullable.
SettingValue = bool | int | str | dict[str, Any] | list[Any] | None

# Canonical E.164: a leading '+', a non-zero country-code digit, then up to 14
# more. No spaces, dashes or parentheses - those are presentation, and storing
# them would mean two spellings of one number and a `wa.me` link that breaks on
# one of them.
# ASCII digits only: `\d` would also match Arabic-Indic and full-width digits,
# which no dialler or wa.me link accepts (BUG-34).
_E164 = re.compile(r"^\+[1-9][0-9]{0,14}$")

_FORMAT_FREE: Final = "free"
_FORMAT_E164: Final = "e164"

# V1 currency, fixed by ADR-008. Money settings carry it explicitly anyway so
# the stored value is self-describing rather than relying on a global constant.
_CURRENCY: Final = "USD"


@dataclass(frozen=True)
class SettingDefinition:
    """One registry entry. Frozen because it is a declaration, not state."""

    key: str
    type: SettingType
    description: str
    default: SettingValue
    is_public: bool = False
    unit: str | None = None
    # For `money` these bound `amount_cents`, not the object.
    minimum: int | None = None
    maximum: int | None = None
    # Whether JSON `null` is an acceptable value. True only where the SRS calls
    # the setting optional, or where the real value is still awaited from the
    # client and inventing a placeholder would publish fiction to customers.
    nullable: bool = False
    max_length: int | None = None
    text_format: str = _FORMAT_FREE


_DEFINITIONS: Final[tuple[SettingDefinition, ...]] = (
    SettingDefinition(
        key="accepting_orders",
        type=SettingType.BOOLEAN,
        description=(
            "Global kill switch. False blocks new checkout with 503 ORDERS_PAUSED; "
            "payments already in flight are unaffected."
        ),
        # Closed until an administrator opens the shop. A fresh deployment has
        # no catalogue, no shipping zones and no verified payment provider, so
        # defaulting open would mean the only window in which checkout is
        # unconfigured is also the one in which it is reachable.
        default=False,
        is_public=True,
    ),
    SettingDefinition(
        key="offer_response_window",
        type=SettingType.DURATION,
        description="How long the party whose turn it is has to respond before an offer expires.",
        default=172_800,  # 48 hours
        unit="seconds",
        minimum=3_600,  # 1 hour
        maximum=604_800,  # 7 days
    ),
    SettingDefinition(
        key="offer_checkout_window",
        type=SettingType.DURATION,
        description="How long an accepted offer stays purchasable at its frozen price.",
        default=86_400,  # 24 hours
        unit="seconds",
        minimum=3_600,
        maximum=604_800,
    ),
    SettingDefinition(
        key="offer_rejection_cooldown",
        type=SettingType.DURATION,
        description=(
            "Wait after a rejection before the same customer may offer on that product again."
        ),
        default=604_800,  # 7 days
        unit="seconds",
        # Zero is meaningful here and is deliberately allowed: it means "no
        # cooldown", which is a legitimate operating choice rather than a
        # degenerate value.
        minimum=0,
        maximum=2_592_000,  # 30 days
    ),
    SettingDefinition(
        key="minimum_offer_percentage",
        type=SettingType.INTEGER,
        description=(
            "Offer floor as a whole percentage of list price. Offers below it are rejected "
            "at submission with 422 OFFER_BELOW_MINIMUM."
        ),
        default=70,
        unit="percent",
        minimum=0,
        maximum=100,
    ),
    SettingDefinition(
        key="checkout_hold_period",
        type=SettingType.DURATION,
        description="How long an unpaid checkout is held before it is cancelled automatically.",
        default=1_800,  # 30 minutes
        unit="seconds",
        minimum=300,  # 5 minutes
        maximum=7_200,  # 2 hours
    ),
    SettingDefinition(
        key="manual_payment_hold_period",
        type=SettingType.DURATION,
        description=(
            "How long an unpaid order on the manual payment provider is held before it is "
            "cancelled automatically (ADR-049)."
        ),
        default=604_800,  # 7 days
        unit="seconds",
        minimum=3_600,  # 1 hour
        maximum=2_592_000,  # 30 days
    ),
    SettingDefinition(
        key="unverified_account_purge_period",
        type=SettingType.DURATION,
        description=(
            "Age at which a never-verified account is physically deleted by the "
            "purge_unverified_accounts job."
        ),
        # 30 days, matching exactly what the job did from a source-code constant
        # before this slice, so deployment changes no behaviour.
        default=2_592_000,
        unit="seconds",
        minimum=604_800,  # 7 days
        maximum=7_776_000,  # 90 days
    ),
    # VS-023b (ADR-019): `daily_download_cap` was removed: no file is downloaded.
    # VS-028 (ADR-024 d7, BR-145). `free_shipping_threshold` was removed: no shipping is charged.
    SettingDefinition(
        key="cash_payment_enabled",
        type=SettingType.BOOLEAN,
        description=(
            "Whether checkout offers cash on delivery or at pickup. Existing cash orders "
            "are unaffected."
        ),
        default=True,
        is_public=True,
    ),
    SettingDefinition(
        key="cash_max_open_orders",
        type=SettingType.INTEGER,
        description=(
            "Unpaid, uncancelled cash orders allowed per customer or contact phone at once."
        ),
        default=1,
        unit="cash orders per customer or contact phone",
        minimum=1,
        maximum=10,
    ),
    SettingDefinition(
        key="cash_max_order_total",
        type=SettingType.MONEY,
        description="Highest recomputed order total that may be paid in cash.",
        # Public: checkout must say why cash is unavailable. At least 1 cent (no $0 cash).
        default={"amount_cents": 10_000, "currency": "USD"},
        is_public=True,
        unit="cents",
        minimum=1,
        maximum=1_000_000,
    ),
    SettingDefinition(
        key="pickup_address",
        type=SettingType.STRING,
        description="Workshop address shown at checkout and in the ready-for-pickup notification.",
        # Awaiting the client (SRS 30.2). Null rather than a placeholder: this
        # value is served publicly, and a plausible-looking fake address is
        # worse than a visibly absent one.
        default=None,
        is_public=True,
        nullable=True,
        max_length=500,
    ),
    SettingDefinition(
        key="pickup_hours",
        type=SettingType.STRING,
        description="Workshop opening hours, shown alongside the pickup address.",
        default=None,
        is_public=True,
        nullable=True,
        max_length=200,
    ),
    SettingDefinition(
        key="whatsapp_number",
        type=SettingType.STRING,
        description=(
            "Business WhatsApp number in canonical E.164, used by the floating button "
            "and product click-to-chat."
        ),
        default=None,
        is_public=True,
        nullable=True,
        max_length=16,  # '+' plus at most 15 digits
        text_format=_FORMAT_E164,
    ),
    SettingDefinition(
        key="security_token_retention_period",
        type=SettingType.DURATION,
        description=(
            "Age past expires_at at which a verification or password-reset token is deleted "
            "by purge_expired_security_records."
        ),
        # 7 days: an expired link keeps answering 410 for a week, then 400 (VS-046).
        default=604_800,
        unit="seconds",
        minimum=86_400,  # 1 day
        maximum=7_776_000,  # 90 days
    ),
    SettingDefinition(
        key="session_retention_period",
        type=SettingType.DURATION,
        description=(
            "Age past a session's end (expiry or revocation, whichever came first) at which "
            "the row is deleted by purge_expired_security_records."
        ),
        # 30 days: the row holds ip_hash and user_agent; the audit log keeps the events.
        default=2_592_000,
        unit="seconds",
        minimum=86_400,  # 1 day
        maximum=7_776_000,  # 90 days
    ),
    SettingDefinition(
        key="custom_request_attachment_retention",
        type=SettingType.DURATION,
        description=(
            "Age at which a Bring Your Idea reference image is purged by "
            "purge_expired_attachments; stamped on each attachment when it is submitted."
        ),
        # 90 days (VS-034, SRS 30.3 design-time decision); a change affects new uploads only.
        default=7_776_000,
        unit="seconds",
        minimum=86_400,  # 1 day
        maximum=31_536_000,  # 365 days
    ),
)

REGISTRY: Final[dict[str, SettingDefinition]] = {d.key: d for d in _DEFINITIONS}

# The public allowlist, derived from the registry rather than written out twice.
# Ordered for a stable response and a stable test.
PUBLIC_KEYS: Final[tuple[str, ...]] = tuple(d.key for d in _DEFINITIONS if d.is_public)

ALL_KEYS: Final[tuple[str, ...]] = tuple(d.key for d in _DEFINITIONS)


def definition_for(key: str) -> SettingDefinition:
    """The registry entry for `key`, or `SettingNotFoundError`.

    Every path that accepts a key from a caller goes through here, which is what
    makes "unknown keys cannot be created" a property of the system rather than
    a check somebody remembered to write on one endpoint.
    """
    try:
        return REGISTRY[key]
    except KeyError as exc:
        raise SettingNotFoundError(key) from exc


def _is_strict_int(value: object) -> TypeGuard[int]:
    """`True` is an `int` in Python.

    `isinstance(True, int)` is True, so a naive integer check accepts `true` for
    a numeric setting and reads it as 1 - the same trap ADR-018's `auth_epoch`
    claim had to close. Comparing the exact type is what excludes it.

    Declared as a `TypeGuard` so the caller gets the narrowing too, and does not
    have to launder an `object` back through `int()` - which would happily
    accept the very values this rejects.
    """
    return type(value) is int


def _validate_number(
    definition: SettingDefinition, value: object, *, label: str, reasons: list[str]
) -> None:
    if not _is_strict_int(value):
        reasons.append(
            f"{label} must be a whole number, not {type(value).__name__}"
            " (booleans, decimals and numeric strings are not accepted)"
        )
        return
    number = value
    if definition.minimum is not None and number < definition.minimum:
        reasons.append(f"{label} must be at least {definition.minimum}")
    if definition.maximum is not None and number > definition.maximum:
        reasons.append(f"{label} must be at most {definition.maximum}")


def _validate_money(definition: SettingDefinition, value: object, reasons: list[str]) -> None:
    if not isinstance(value, dict):
        reasons.append("value must be an object with amount_cents and currency")
        return
    expected_keys = {"amount_cents", "currency"}
    if set(value) != expected_keys:
        reasons.append("value must have exactly the keys amount_cents and currency")
        return
    _validate_number(definition, value["amount_cents"], label="amount_cents", reasons=reasons)
    if value["currency"] != _CURRENCY:
        reasons.append(f"currency must be {_CURRENCY!r} (ADR-008 fixes the V1 currency)")


def _validate_string(
    definition: SettingDefinition, value: object, reasons: list[str]
) -> str | None:
    if not isinstance(value, str):
        reasons.append(f"value must be a string, not {type(value).__name__}")
        return None
    # Refused, not stripped: PostgreSQL cannot store NUL at all, and no other
    # control character belongs in a displayed setting (BUG-03). Line breaks
    # stay allowed - an address or opening hours may span lines.
    if has_control_characters(value, allow_line_breaks=True):
        reasons.append("value must not contain control characters")
        return None
    trimmed = value.strip()
    # Invisible format characters (zero-width space and joiners, BOM, word
    # joiner - Unicode category Cf) survive str.strip(), so a value made only
    # of them rendered as blank yet passed as non-empty (BUG-33).
    if not "".join(ch for ch in trimmed if unicodedata.category(ch) != "Cf").strip():
        reasons.append("value must not be empty or whitespace only")
        return None
    if definition.max_length is not None and len(trimmed) > definition.max_length:
        reasons.append(f"value must be at most {definition.max_length} characters")
    if definition.text_format == _FORMAT_E164 and not _E164.match(trimmed):
        reasons.append(
            "value must be a canonical E.164 number: a leading '+', then up to 15 digits, "
            "with no spaces or separators"
        )
    return trimmed


def validate_value(key: str, value: SettingValue) -> SettingValue:
    """Check a submitted value against its key and return the value to store.

    Returns rather than merely checking, because validation normalises:
    a string is stored trimmed, so `" +9613 "` and `"+9613"` cannot both end up
    in the table as different values of the same setting.

    Raises `SettingNotFoundError` for an unregistered key and
    `InvalidSettingValueError` carrying *every* reason it failed - an admin
    fixing a money object with both a bad currency and a negative amount should
    see both at once.
    """
    definition = definition_for(key)
    reasons: list[str] = []

    if value is None:
        if definition.nullable:
            return None
        reasons.append("value must not be null for this setting")
        raise InvalidSettingValueError(key, reasons)

    match definition.type:
        case SettingType.BOOLEAN:
            # `type(...) is bool` and not `isinstance`: 0 and 1 are not booleans
            # here, and accepting them would make `1` and `true` two spellings
            # of one stored value.
            if type(value) is not bool:
                reasons.append(f"value must be true or false, not {type(value).__name__}")
        case SettingType.INTEGER | SettingType.DURATION:
            _validate_number(definition, value, label="value", reasons=reasons)
        case SettingType.MONEY:
            _validate_money(definition, value, reasons)
        case SettingType.STRING:
            trimmed = _validate_string(definition, value, reasons)
            if not reasons and trimmed is not None:
                return trimmed
        case SettingType.JSON:
            # Free-form by definition. No V1 setting uses it; the branch exists
            # because the type does, and silently rejecting a declared type
            # would be worse than accepting what it promises. NUL is still
            # refused: JSONB cannot store it (BUG-03).
            if json_contains_nul(value):
                reasons.append("value must not contain NUL characters")

    if reasons:
        raise InvalidSettingValueError(key, reasons)
    return value
