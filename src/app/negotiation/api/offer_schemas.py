"""Offer payloads (api-endpoints.md 13, 21, 29.7, `OfferDetail`; docs/offers.md)."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.api.text import MultilineStr
from app.catalog.public import PriceRead, PublicImage
from app.negotiation.application.services.offer_queries import OfferView
from app.negotiation.domain.enums import OfferAction, OfferActor, OfferStatus, OfferTurn
from app.negotiation.domain.offers import MAX_MESSAGE_LENGTH, OfferRound

PG_BIGINT_MAX = 9_223_372_036_854_775_807
AmountCents = Annotated[StrictInt, Field(ge=1, le=PG_BIGINT_MAX)]


def _price(cents: int | None, currency: str) -> PriceRead | None:
    return PriceRead(amount_cents=cents, currency=currency) if cents is not None else None


class OfferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    amount_cents: AmountCents = Field(
        description="At least minimum_offer_percentage of the list price, at most the price."
    )
    currency: Literal["USD"]
    message: MultilineStr | None = Field(default=None, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class OfferProductRead(BaseModel):
    id: UUID
    name: str | None = Field(description="Null only if the product row is gone (never in V1).")
    slug: str | None
    cover_image: PublicImage | None


class OfferCustomerRead(BaseModel):
    id: UUID
    email: str | None


class OfferRoundRead(BaseModel):
    sequence: int
    actor: OfferActor
    action: OfferAction
    amount: PriceRead | None
    message: str | None
    created_at: datetime

    @classmethod
    def of(cls, row: OfferRound) -> Self:
        return cls(
            sequence=row.sequence,
            actor=row.actor,
            action=row.action,
            amount=_price(row.amount_cents, row.currency or "USD"),
            message=row.message,
            created_at=row.created_at,
        )


class OfferSummaryRead(BaseModel):
    id: UUID
    product: OfferProductRead
    status: OfferStatus
    turn: OfferTurn | None = Field(description="Whose answer is awaited; null once closed.")
    current_amount: PriceRead
    agreed_amount: PriceRead | None
    responds_by: datetime | None = Field(
        description="The turn's deadline; the offer expires once it is reached."
    )
    checkout_expires_at: datetime | None
    created_at: datetime

    @classmethod
    def _fields(cls, view: OfferView, media_base_url: str) -> dict[str, object]:
        o, p = view.offer, view.product
        cover = PublicImage.from_entity(p.cover, media_base_url) if p and p.cover else None
        return {
            "id": o.id,
            "product": OfferProductRead(
                id=o.product_id,
                name=p.name if p else None,
                slug=p.slug if p else None,
                cover_image=cover,
            ),
            "status": o.status,
            "turn": o.turn,
            "current_amount": PriceRead(amount_cents=o.current_amount_cents, currency=o.currency),
            "agreed_amount": _price(o.agreed_amount_cents, o.currency),
            "responds_by": o.responds_by,
            "checkout_expires_at": o.checkout_expires_at,
            "created_at": o.created_at,
        }

    @classmethod
    def of(cls, view: OfferView, media_base_url: str) -> Self:
        return cls.model_validate(cls._fields(view, media_base_url))


class OfferDetailRead(OfferSummaryRead):
    initial_amount: PriceRead
    cooldown_until: datetime | None = Field(description="Set on a rejected offer (BR-089).")
    updated_at: datetime
    rounds: list[OfferRoundRead] = Field(description="The complete, append-only history.")
    allowed_actions: list[str] = Field(
        description="Empty until VS-040 adds counter, accept, reject and withdraw."
    )

    @classmethod
    def _detail(cls, view: OfferView, media_base_url: str) -> dict[str, object]:
        o = view.offer
        return {
            **cls._fields(view, media_base_url),
            "initial_amount": PriceRead(amount_cents=o.initial_amount_cents, currency=o.currency),
            "cooldown_until": o.cooldown_until,
            "updated_at": o.updated_at,
            "rounds": [OfferRoundRead.of(row) for row in view.rounds],
            "allowed_actions": [],
        }

    @classmethod
    def of(cls, view: OfferView, media_base_url: str) -> Self:
        return cls.model_validate(cls._detail(view, media_base_url))


class OfferPage(BaseModel):
    items: list[OfferSummaryRead]
    next_cursor: str | None


class AdminOfferSummaryRead(OfferSummaryRead):
    customer: OfferCustomerRead

    @classmethod
    def of(cls, view: OfferView, media_base_url: str) -> Self:
        customer = OfferCustomerRead(id=view.offer.user_id, email=view.customer_email)
        return cls.model_validate({**cls._fields(view, media_base_url), "customer": customer})


class AdminOfferDetailRead(OfferDetailRead):
    customer: OfferCustomerRead

    @classmethod
    def of(cls, view: OfferView, media_base_url: str) -> Self:
        customer = OfferCustomerRead(id=view.offer.user_id, email=view.customer_email)
        return cls.model_validate({**cls._detail(view, media_base_url), "customer": customer})


class AdminOfferPage(BaseModel):
    items: list[AdminOfferSummaryRead]
    next_cursor: str | None
