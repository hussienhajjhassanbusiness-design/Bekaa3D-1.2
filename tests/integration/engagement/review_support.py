"""Helpers for the VS-036 review tests: the routes over HTTP, and probes for a review's
stored badge and a product's aggregates. One HTTP client at a time (cancel_support)."""

import uuid
from decimal import Decimal
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import client_for, csrf, login

REVIEWS = "/api/v1/reviews"
MINE = "/api/v1/me/reviews"


def public_path(slug: str) -> str:
    return f"/api/v1/products/{slug}/reviews"


def post_review(
    client: TestClient, product_id: uuid.UUID, rating: int = 5, body: str | None = None
) -> httpx.Response:
    payload: dict[str, Any] = {"product_id": str(product_id), "rating": rating}
    if body is not None:
        payload["body"] = body
    response: httpx.Response = client.post(REVIEWS, json=payload, headers=csrf(client))
    return response


def patch_review(client: TestClient, review_id: str, **body: Any) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"{REVIEWS}/{review_id}", json=body, headers=csrf(client)
    )
    return response


def delete_review(client: TestClient, review_id: str) -> httpx.Response:
    response: httpx.Response = client.delete(f"{REVIEWS}/{review_id}", headers=csrf(client))
    return response


async def email_of(db: AsyncSession, user_id: uuid.UUID) -> str:
    return str(await db.scalar(text("SELECT email FROM users WHERE id = :u"), {"u": user_id}))


async def review_as(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID, rating: int = 5
) -> dict[str, Any]:
    """The user posts a review in their own client; returns the 201 body."""
    email = await email_of(db, user_id)
    with client_for(main_app) as client:
        login(client, email)
        response = post_review(client, product_id, rating)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def product_of_line(engine: AsyncEngine, line_id: uuid.UUID) -> uuid.UUID:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT product_id FROM order_items WHERE id = :i"), {"i": line_id}
        )
    assert isinstance(found, uuid.UUID)
    return found


async def slug_of(engine: AsyncEngine, product_id: uuid.UUID) -> str:
    async with engine.connect() as conn:
        return str(
            await conn.scalar(text("SELECT slug FROM products WHERE id = :p"), {"p": product_id})
        )


async def review_row(engine: AsyncEngine, review_id: str | uuid.UUID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT id, rating, body, is_verified_purchase, is_hidden, deleted_at,"
                    " created_at, updated_at FROM reviews WHERE id = :r"
                ),
                {"r": uuid.UUID(str(review_id))},
            )
        ).one()


async def badge(engine: AsyncEngine, review_id: str | uuid.UUID) -> bool:
    return bool((await review_row(engine, review_id)).is_verified_purchase)


async def product_facts(engine: AsyncEngine, product_id: uuid.UUID) -> Any:
    """Aggregates, `version`, `updated_at`, and `xmin` (changes on any UPDATE of the row)."""
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT average_rating, review_count, version, updated_at,"
                    " xmin::text AS xmin FROM products WHERE id = :p"
                ),
                {"p": product_id},
            )
        ).one()


async def fresh_totals(engine: AsyncEngine, product_id: uuid.UUID) -> tuple[Decimal, int]:
    """A fresh AVG / COUNT over visible reviews, rounded like the stored column."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT COALESCE(ROUND(AVG(rating)::numeric, 2), 0.00) AS a, count(*) AS n"
                    " FROM reviews WHERE product_id = :p AND deleted_at IS NULL"
                    " AND NOT is_hidden"
                ),
                {"p": product_id},
            )
        ).one()
    return Decimal(row.a).quantize(Decimal("0.01")), int(row.n)


async def stored_totals(engine: AsyncEngine, product_id: uuid.UUID) -> tuple[Decimal, int]:
    facts = await product_facts(engine, product_id)
    return Decimal(facts.average_rating), int(facts.review_count)


async def execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)
