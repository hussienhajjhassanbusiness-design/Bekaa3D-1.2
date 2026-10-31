"""Cart payloads (api-endpoints.md 10.1, 29.4; VS-022 plan §2). No total is exposed:
checkout recomputes it from live prices (plan §3.6)."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.catalog.application.ports import ProductType, PurchaseRefusal
from app.catalog.public import PriceRead, PublicImage
from app.ordering.application.services.cart import CartView
from app.ordering.domain.cart_rules import CartLineView
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.payment_methods import in_order, shared_methods

PG_INT_MAX = 2_147_483_647
Quantity = Annotated[StrictInt, Field(ge=1, le=PG_INT_MAX)]


class CartItemAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Quantity = 1


class CartItemQuantityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Quantity


class CartLineRead(BaseModel):
    product_id: UUID
    product_type: ProductType
    name: str | None = Field(description="Null only if the product row is gone (never in V1).")
    slug: str | None
    cover_image: PublicImage | None
    quantity: int
    snapshot_price: PriceRead = Field(description="Display only; checkout charges the live price.")
    current_price: PriceRead | None
    price_changed: bool
    max_quantity: int | None
    over_cap: bool = Field(description="Above the product's current cap; checkout refuses it.")
    purchasable: bool
    unpurchasable_reason: PurchaseRefusal | None

    @classmethod
    def of(cls, view: CartLineView, media_base_url: str) -> Self:
        line = view.line
        current = view.current_price_cents
        return cls(
            product_id=line.product_id,
            product_type=line.product_type,
            name=view.name,
            slug=view.slug,
            cover_image=PublicImage.from_entity(view.cover, media_base_url) if view.cover else None,
            quantity=line.quantity,
            snapshot_price=PriceRead(
                amount_cents=line.price_snapshot_cents, currency=line.currency
            ),
            current_price=PriceRead(amount_cents=current, currency=line.currency)
            if current is not None
            else None,
            price_changed=view.price_changed,
            max_quantity=view.max_quantity,
            over_cap=view.over_cap,
            purchasable=view.purchasable,
            unpurchasable_reason=view.refusal,
        )


class CartRead(BaseModel):
    id: UUID | None = Field(description="Null until the customer's first cart write.")
    items: list[CartLineRead]
    contains_physical: bool
    contains_digital: bool
    payment_methods: list[PaymentMethod] = Field(
        description="Methods every line's product accepts; empty: order them separately."
    )
    updated_at: datetime | None

    @classmethod
    def of(cls, view: CartView, media_base_url: str) -> Self:
        types = {v.line.product_type for v in view.lines}
        return cls(
            id=view.cart.id if view.cart else None,
            items=[CartLineRead.of(v, media_base_url) for v in view.lines],
            contains_physical=ProductType.PHYSICAL in types,
            contains_digital=ProductType.STL in types,
            payment_methods=in_order(shared_methods(v.payment_methods for v in view.lines)),
            updated_at=view.cart.updated_at if view.cart else None,
        )
