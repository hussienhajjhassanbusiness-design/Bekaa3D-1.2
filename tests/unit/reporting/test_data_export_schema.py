"""VS-044: every exported field is named here, so a new one is a deliberate change (ADR-046)."""

from dataclasses import fields

import pytest

from app.reporting.api.export_schemas import DataExportRead
from app.reporting.domain import data_export as d

ALLOWED: dict[type, set[str]] = {
    d.ExportProfile: {"id", "email", "role", "email_verified", "email_verified_at", "created_at"},
    d.ExportAddress: {
        "id", "label", "recipient_name", "phone", "governorate", "city", "area", "street",
        "landmark_notes", "is_default", "created_at", "updated_at", "deleted", "deleted_at",
    },
    d.ExportOrder: {
        "id", "order_number", "source", "status", "payment_method", "fulfillment_method",
        "payment_due", "amount_due", "subtotal", "tax", "total", "delivery_address",
        "contact_phone", "delivery_email", "customer_note", "estimated_dispatch_at",
        "placed_at", "completed_at", "cancelled_at", "lines", "payment", "refunds",
        "status_history",
    },
    d.ExportOrderLine: {
        "id", "product_id", "product_type", "name", "offer_id", "unit_price", "quantity",
        "line_total", "fulfillment_status", "fulfilled_at", "cancelled_at",
        "receipt_confirmed_at", "problem_reported_at",
    },
    d.ExportStatusChange: {"order_item_id", "from_status", "to_status", "at"},
    d.ExportDeliveryAddress: {
        "recipient_name", "governorate", "city", "area", "street", "landmark_notes",
    },
    d.ExportPayment: {"provider", "status", "amount"},
    d.ExportRefund: {"kind", "status", "amount", "created_at"},
    d.ExportReview: {
        "id", "product_id", "product_name", "rating", "body", "is_verified_purchase",
        "is_hidden", "created_at", "updated_at", "deleted", "deleted_at",
    },
    d.ExportOffer: {
        "id", "product_id", "product_name", "status", "turn", "initial_amount",
        "current_amount", "agreed_amount", "responds_by", "accepted_at", "checkout_expires_at",
        "cooldown_until", "created_at", "updated_at", "rounds",
    },
    d.ExportOfferRound: {"sequence", "actor", "action", "amount", "message", "created_at"},
    d.ExportContactMessage: {"subject", "message", "created_at"},
    d.Money: {"amount_cents", "currency"},
}  # fmt: skip

FORBIDDEN = {
    "admin_note", "admin_notes", "password_hash", "contact_phone_hash", "phone_hash", "ip_hash",
    "provider_payment_id", "provider_metadata", "redirect_url", "recorded_by", "delivered_by",
    "actor_user_id", "reason", "settlement_reference", "settlement_note", "failure_reason",
    "remind_at", "auth_epoch", "user_id", "email_snapshot",
}  # fmt: skip


@pytest.mark.parametrize("record", list(ALLOWED), ids=lambda r: r.__name__)
def test_each_record_exports_exactly_its_allowlist(record: type) -> None:
    assert {f.name for f in fields(record)} == ALLOWED[record]


@pytest.mark.parametrize("record", list(ALLOWED), ids=lambda r: r.__name__)
def test_no_record_carries_an_internal_field(record: type) -> None:
    assert not {f.name for f in fields(record)} & FORBIDDEN


def test_contact_messages_carry_no_contact_details_or_status() -> None:
    assert not {f.name for f in fields(d.ExportContactMessage)} & {
        "status", "email", "phone", "name", "order_id", "id",
    }  # fmt: skip


def test_the_document_is_the_profile_and_exactly_the_six_sets() -> None:
    assert list(DataExportRead.model_fields) == [
        "format_version", "exported_at", "profile", *d.SECTIONS,
    ]  # fmt: skip
    assert d.SECTIONS == ("addresses", "orders", "reviews", "offers", "contact_messages")


def test_every_record_type_is_covered_by_the_allowlist() -> None:
    declared = {v for v in vars(d).values() if isinstance(v, type) and v.__module__ == d.__name__}
    assert declared == set(ALLOWED)


def test_money_refuses_a_non_integer_amount() -> None:
    from decimal import Decimal

    with pytest.raises(TypeError):
        d.Money(Decimal(1000), "USD")  # type: ignore[arg-type]
    assert d.Money(1000, "USD").amount_cents == 1000
