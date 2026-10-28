"""Seeding for the VS-044 export tests: one customer holding every data set, with internal
values set to sentinels so a leak shows up as a substring of the body."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_phone
from app.identity.domain.enums import UserRole
from app.main import app as main_app
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import client_for, create_user, csrf, mfa_admin
from tests.integration.fulfillment.delivery_support import line_of
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.negotiation.offer_support import seed_offer
from tests.integration.payments.refund_support import act, create, ok

EXPORT = "/api/v1/me/export"


@dataclass
class Seeded:
    user_id: uuid.UUID
    email: str
    paid_order: uuid.UUID
    cash_order: uuid.UUID
    stl_line: uuid.UUID
    physical_line: uuid.UUID
    ids: set[str] = field(default_factory=set)  # every exported row id of this customer
    sentinels: set[str] = field(default_factory=set)  # values that must never be exported
    own_text: set[str] = field(default_factory=set)  # values the customer wrote


async def _run(db: AsyncSession, sql: str, **params: Any) -> Any:
    found = await db.execute(text(sql), params)
    await db.commit()
    return found


async def seed_customer(db: AsyncSession, tag: str) -> Seeded:
    """Each `tag` makes this customer's sentinels distinct from another's."""
    user = await create_user(db)
    admin = await create_user(db, role=UserRole.ADMIN)
    paid = await seed_physical_order(
        db,
        user_id=user.id,
        payment_method="online",
        payment_status="paid",
        line_states=("delivered",),
        stl_line="delivered",
        email=user.email,
    )
    cash = await seed_physical_order(db, user_id=user.id, line_states=("pending",))
    stl_line = await line_of(db, paid.order_id, "stl")
    s = Seeded(user.id, user.email, paid.order_id, cash.order_id, stl_line, paid.line_ids[0])
    s.sentinels |= {user.password_hash, str(admin.id), hash_phone(paid.phone)}
    s.ids |= {
        str(paid.order_id),
        str(cash.order_id),
        str(stl_line),
        *map(str, paid.line_ids + cash.line_ids),
    }

    note, ref, meta, why = (f"SENTINEL-{k}-{tag}" for k in ("NOTE", "PREF", "META", "WHY"))
    s.sentinels |= {note, ref, meta, why}
    await _run(db, "UPDATE orders SET admin_note = :n WHERE id = :o", n=note, o=paid.order_id)
    await _run(
        db,
        "UPDATE payments SET provider_payment_id = :r,"
        " provider_metadata = jsonb_build_object('secret', CAST(:m AS text)) WHERE order_id = :o",
        r=ref,
        m=meta,
        o=paid.order_id,
    )
    await _run(
        db,
        "INSERT INTO order_status_history (order_id, order_item_id, from_status, to_status,"
        " actor_user_id, reason) VALUES (:o, :i, 'shipped', 'delivered', :a, :w)",
        o=paid.order_id,
        i=paid.line_ids[0],
        a=admin.id,
        w=why,
    )
    s.ids |= await _addresses(db, user.id, tag)
    s.ids |= await _reviews(db, user.id)
    s.ids |= await _offers(db, user.id, tag, s)
    await _contact_messages(db, user.id, paid.order_id, tag, s)
    return s


async def _addresses(db: AsyncSession, user_id: uuid.UUID, tag: str) -> set[str]:
    ids = set()
    for label, deleted in ((f"Home {tag}", None), (f"Old {tag}", datetime.now(UTC))):
        row = await _run(
            db,
            "INSERT INTO addresses (user_id, label, recipient_name, phone, governorate, city,"
            " landmark_notes, is_default, deleted_at) VALUES (:u, :l, 'Rana', '+96171123456',"
            " 'beqaa', 'Zahle', 'Blue door', :d, :x) RETURNING id",
            u=user_id,
            l=label,
            d=deleted is None,
            x=deleted,
        )
        ids.add(str(row.scalar_one()))
    return ids


async def _reviews(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    refs = await seed_refs(db)
    ids = set()
    for deleted in (None, datetime.now(UTC)):
        product = (await seed_product(db, refs)).id
        row = await _run(
            db,
            "INSERT INTO reviews (user_id, product_id, rating, body, is_verified_purchase,"
            " deleted_at) VALUES (:u, :p, 4, 'Solid print', false, :d) RETURNING id",
            u=user_id,
            p=product,
            d=deleted,
        )
        ids.add(str(row.scalar_one()))
    return ids


async def _offers(db: AsyncSession, user_id: uuid.UUID, tag: str, s: Seeded) -> set[str]:
    product = (await seed_product(db, await seed_refs(db))).id
    offer = await seed_offer(db, user_id=user_id, product_id=product, status="rejected")
    reply = f"Too low, sorry {tag}"
    await _run(
        db,
        "INSERT INTO offer_rounds (offer_id, sequence, actor, action, message)"
        " VALUES (:o, 2, 'admin', 'rejected', :m)",
        o=offer,
        m=reply,
    )
    s.own_text.add(reply)
    return {str(offer)}


async def _contact_messages(
    db: AsyncSession, user_id: uuid.UUID, order_id: uuid.UUID, tag: str, s: Seeded
) -> None:
    name, mail, phone = f"SENTINEL-NAME-{tag}", f"sentinel-{tag}@example.com", f"+9617{tag}"
    words = f"My parcel arrived broken {tag}"
    await _run(
        db,
        "INSERT INTO contact_messages (name, email, phone, subject, message, user_id, order_id,"
        " status) VALUES (:n, :e, :ph, 'Problem with my order', :m, :u, :o, 'replied')",
        n=name,
        e=mail,
        ph=phone[:20],
        m=words,
        u=user_id,
        o=order_id,
    )
    s.sentinels |= {name, mail}
    s.own_text.add(words)


async def refund_settle_and_void(
    db: AsyncSession, order_id: uuid.UUID, line_id: uuid.UUID, tag: str
) -> set[str]:
    """A settled 300 refund and a voided 100 one, on an admin client of their own (one
    TestClient at a time); returns their internal values."""
    reason, reference, note, void = (
        f"SENTINEL-{k}-{tag}" for k in ("REASON", "SREF", "SNOTE", "VOID")
    )
    with client_for(main_app) as admin:
        await mfa_admin(admin, db)
        settled = ok(create(admin, order_id, [(line_id, 300)], reason=reason), 201)
        ok(act(admin, settled["id"], "settle", {"reference": reference, "note": note}))
        voided = ok(create(admin, order_id, [(line_id, 100)], reason=reason), 201)
        ok(act(admin, voided["id"], "void", {"reason": void}))
    return {reason, reference, note, void}


def export(client: TestClient, headers: dict[str, str] | None = None) -> httpx.Response:
    """With this session's CSRF header unless `headers` replaces it (ADR-046 d11)."""
    response: httpx.Response = client.get(
        EXPORT, headers=csrf(client) if headers is None else headers
    )
    return response
