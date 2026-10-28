"""Seeding for the VS-045 deletion tests: one customer with a closed order history and a row
in every table deletion touches, each personal value tagged so a trace shows up in a scan."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.platform.domain.entities import REDACTED
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, create_user, csrf
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.negotiation.offer_support import seed_offer

ME = "/api/v1/me"


@dataclass
class Customer:
    user_id: uuid.UUID
    email: str
    password_hash: str
    orders: list[uuid.UUID]
    products: list[uuid.UUID] = field(default_factory=list)  # wishlisted, count 1 each
    offers: list[uuid.UUID] = field(default_factory=list)  # live
    pii: set[str] = field(default_factory=set)  # personal values no table may keep


async def run(db: AsyncSession, sql: str, **params: Any) -> Any:
    found = await db.execute(text(sql), params)
    await db.commit()
    return found


async def seed_customer(db: AsyncSession, tag: str | None = None) -> Customer:
    """Closed orders only (one completed with an STL line, one cancelled cash), so deletion
    is allowed; `tag` makes every personal value unique to this customer."""
    tag = tag or uuid.uuid4().hex[:10]
    user = await create_user(db)
    done = await seed_physical_order(
        db,
        user_id=user.id,
        payment_method="online",
        payment_status="paid",
        line_states=("delivered",),
        stl_line="delivered",
        order_status="completed",
        email=user.email,
    )
    cancelled = await seed_physical_order(
        db,
        user_id=user.id,
        line_states=("cancelled",),
        order_status="cancelled",
        email=user.email,
    )
    c = Customer(user.id, user.email, user.password_hash, [done.order_id, cancelled.order_id])
    c.pii |= {user.email, done.phone, cancelled.phone}
    name, street, note = f"Rana {tag}", f"Street {tag}", f"Leave at gate {tag}"
    await run(
        db,
        "UPDATE orders SET recipient_name = :n, street = :s, area = :s, customer_note = :c,"
        " landmark_notes = :s, admin_note = 'Called twice' WHERE user_id = :u",
        n=name,
        s=street,
        c=note,
        u=user.id,
    )
    c.pii |= {name, street, note}
    await _addresses(db, c, tag)
    await _wishlist_and_cart(db, c)
    await _offers(db, c)
    await _messages_and_mail(db, c, tag)
    await _tokens(db, c)
    return c


async def _addresses(db: AsyncSession, c: Customer, tag: str) -> None:
    for n, deleted in enumerate((None, datetime.now(UTC))):
        phone = f"+9617{uuid.uuid4().int % 10**7:07d}"
        await run(
            db,
            "INSERT INTO addresses (user_id, label, recipient_name, phone, governorate, city,"
            " street, landmark_notes, is_default, deleted_at) VALUES (:u, 'Home', :r, :p,"
            " 'beqaa', :city, :st, :lm, :d, :x)",
            u=c.user_id,
            r=f"Addr name {n} {tag}",
            p=phone,
            city=f"City {n} {tag}",
            st=f"Addr street {n} {tag}",
            lm=f"Blue door {n} {tag}",
            d=deleted is None,
            x=deleted,
        )
        c.pii |= {phone, f"Addr name {n} {tag}", f"Addr street {n} {tag}", f"Blue door {n} {tag}"}


async def _wishlist_and_cart(db: AsyncSession, c: Customer) -> None:
    refs = await seed_refs(db)
    for _ in range(2):
        product = (await seed_product(db, refs, type=ProductType.PHYSICAL)).id
        await run(
            db,
            "INSERT INTO wishlist_items (user_id, product_id) VALUES (:u, :p)",
            u=c.user_id,
            p=product,
        )
        await run(db, "UPDATE products SET wishlist_count = 1 WHERE id = :p", p=product)
        c.products.append(product)
    cart = await run(db, "INSERT INTO carts (user_id) VALUES (:u) RETURNING id", u=c.user_id)
    await run(
        db,
        "INSERT INTO cart_items (cart_id, product_id, product_type, quantity, price_snapshot_cents)"
        " VALUES (:c, :p, 'physical', 1, 1000)",
        c=cart.scalar_one(),
        p=c.products[0],
    )


async def _offers(db: AsyncSession, c: Customer) -> None:
    refs = await seed_refs(db)
    for status in ("awaiting_admin", "accepted"):
        product = (await seed_product(db, refs)).id
        c.offers.append(await seed_offer(db, user_id=c.user_id, product_id=product, status=status))


async def _messages_and_mail(db: AsyncSession, c: Customer, tag: str) -> None:
    words, sender, phone = f"My lamp is cracked {tag}", f"Rana sender {tag}", f"+961 3 {tag[:6]}"
    await run(
        db,
        "INSERT INTO contact_messages (name, email, phone, subject, message, user_id, order_id)"
        " VALUES (:n, :e, :ph, 'Problem with my order', :m, :u, :o)",
        n=sender,
        e=c.email,
        ph=phone,
        m=words,
        u=c.user_id,
        o=c.orders[0],
    )
    for status in ("pending", "sent"):
        await run(
            db,
            "INSERT INTO email_outbox (user_id, recipient_email, template, payload, status,"
            " sent_at) VALUES (:u, :e, 'order_placed', jsonb_build_object('name', CAST(:n AS"
            " text)), CAST(:s AS outbox_status), :at)",
            u=c.user_id,
            e=c.email,
            n=sender if status == "pending" else REDACTED,  # sending redacts (mark_sent)
            s=status,
            at=datetime.now(UTC) if status == "sent" else None,
        )
    c.pii |= {words, sender, phone}


async def _tokens(db: AsyncSession, c: Customer) -> None:
    later = datetime.now(UTC) + timedelta(hours=1)
    for table in ("verification_tokens", "password_reset_tokens"):
        await run(
            db,
            f"INSERT INTO {table} (user_id, token_hash, expires_at) VALUES (:u, :h, :x)",
            u=c.user_id,
            h=uuid.uuid4().hex,
            x=later,
        )


def delete_me(
    client: TestClient, password: str = PASSWORD, headers: dict[str, str] | None = None
) -> httpx.Response:
    response: httpx.Response = client.request(
        "DELETE",
        ME,
        json={"current_password": password},
        headers=csrf(client) if headers is None else headers,
    )
    return response


async def one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def traces(engine: AsyncEngine, needles: set[str]) -> dict[str, list[str]]:
    """Every public table whose row text contains a needle, by table."""
    found: dict[str, list[str]] = {}
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename NOT LIKE 'audit_logs_%' AND tablename <> 'alembic_version'"
            )
        )
        tables: list[str] = list(rows.scalars())
        for table in tables:
            for needle in needles:
                hit = await conn.scalar(
                    text(f'SELECT count(*) FROM "{table}" t WHERE t::text ILIKE :n'),
                    {"n": f"%{needle}%"},
                )
                if hit:
                    found.setdefault(table, []).append(needle)
    return found


async def wait_for_waiters(engine: AsyncEngine, pattern: str, count: int) -> None:
    """Block until `count` backends wait on a lock while running a query like `pattern`."""
    deadline = asyncio.get_running_loop().time() + 10.0
    while asyncio.get_running_loop().time() < deadline:
        waiting = await scalar(
            engine,
            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
            " AND datname = current_database() AND query ILIKE :p",
            p=pattern,
        )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.05)
    async with engine.connect() as conn:
        waiting = (
            await conn.execute(
                text(
                    "SELECT wait_event_type, left(query, 300) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND state <> 'idle'"
                )
            )
        ).all()
    raise AssertionError(f"fewer than {count} requests ever waited on {pattern}: {waiting}")
