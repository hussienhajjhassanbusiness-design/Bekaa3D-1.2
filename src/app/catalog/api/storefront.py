"""`GET /api/v1/products` with search (VS-015, VS-016) and `GET /api/v1/products/{slug}`
(docs/storefront-catalogue.md). Public and rate limited; every read is visibility-filtered."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.api.product_cursor import (
    bad_query,
    decode_cursor,
    decode_search_cursor,
    encode_cursor,
)
from app.catalog.api.product_schemas import PG_BIGINT_MAX
from app.catalog.api.reference_data import PUBLIC_RATE_LIMIT, PUBLIC_RATE_WINDOW_SECONDS
from app.catalog.api.storefront_schemas import ProductDetail, ProductListItem, ProductPage
from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import ProductValidationError
from app.catalog.domain.slug import is_canonical_slug
from app.catalog.domain.storefront import (
    MAX_RATING,
    MIN_FULL_TEXT_HITS,
    SearchMode,
    StorefrontFilter,
    StorefrontSort,
    fuzzy_eligible,
    has_trigram_word,
    resolve_sort,
    search_mode_for,
    search_term,
)
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.storefront_query import StorefrontProductQuery
from app.core.config import get_settings
from app.core.rate_limit import rate_limiter
from app.identity.public import not_found_error

public_router = APIRouter(tags=["catalogue"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# The VS-010 public allowance (600/hour per IP), with a counter per route.
_LIST_LIMIT = rate_limiter(
    key_prefix="catalogue:products",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)
_DETAIL_LIMIT = rate_limiter(
    key_prefix="catalogue:product",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)

_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"description": "VALIDATION_ERROR: bad filter, search term, sort, limit or cursor."},
    429: {"description": "RATE_LIMITED."},
}
_DETAIL_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "NOT_FOUND: no visible product has this slug."},
    429: {"description": "RATE_LIMITED."},
}


def _validated[T](build: Callable[..., T], *args: Any, **values: Any) -> T:
    try:
        return build(*args, **values)
    except ProductValidationError as exc:
        errors = [
            {"loc": ("query", field), "msg": reason, "type": "value_error"}
            for field, reason in exc.errors.items()
        ]
        raise RequestValidationError(errors) from exc


async def _eligible(query: StorefrontProductQuery, term: str) -> bool:
    if not has_trigram_word(term):  # Free to check, so most short searches skip the round trip.
        return False
    return fuzzy_eligible(term, excludes_words=await query.excludes_words(term))


async def _first_search_mode(
    query: StorefrontProductQuery, filters: StorefrontFilter, term: str
) -> SearchMode:
    hits = await query.full_text_hits(filters)
    thin = hits < MIN_FULL_TEXT_HITS
    return search_mode_for(hits, eligible=thin and await _eligible(query, term))


@public_router.get(
    "/products",
    response_model=ProductPage,
    dependencies=[Depends(_LIST_LIMIT)],
    summary="Browse visible products",
    responses=_LIST_RESPONSES,
)
async def list_products(
    type: ProductType | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    material_id: UUID | None = Query(default=None),
    colour_id: UUID | None = Query(default=None),
    price_min_cents: int | None = Query(default=None, ge=0, le=PG_BIGINT_MAX),
    price_max_cents: int | None = Query(default=None, ge=0, le=PG_BIGINT_MAX),
    min_rating: Decimal | None = Query(default=None, ge=0, le=float(MAX_RATING)),
    featured: bool | None = Query(default=None),
    q: str | None = Query(
        default=None, description="Search names and descriptions; blank means no search."
    ),
    sort: StorefrontSort | None = Query(
        default=None, description="`-created_at` by default; `-relevance` by default with `q`."
    ),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
) -> ProductPage:
    term = search_term(q)
    filters = _validated(
        StorefrontFilter,
        product_type=type,
        category_id=category_id,
        material_id=material_id,
        colour_id=colour_id,
        price_min_cents=price_min_cents,
        price_max_cents=price_max_cents,
        min_rating=min_rating,
        featured=featured,
        q=term,
    )
    order = _validated(resolve_sort, sort, term)
    query = StorefrontProductQuery(session)
    mode: SearchMode | None = None
    after = None
    if term is None:
        after = decode_cursor(cursor, order)
    elif searched := decode_search_cursor(cursor, order):
        after, mode = searched
        # A forged fuzzy cursor must not reopen a path the first page would refuse.
        if mode is SearchMode.FUZZY and not await _eligible(query, term):
            raise bad_query("cursor", "cursor is not a valid pagination cursor")
    else:
        mode = await _first_search_mode(query, filters, term)
    rows = await query.list_page(
        limit=limit + 1,
        sort=order,
        filters=filters,
        mode=mode or SearchMode.FULL_TEXT,
        after=after,
    )
    page = [item for item, _ in rows[:limit]]
    images = await ProductImageRepository(session).live_for_products(r.product.id for r in page)
    media = get_settings().media_public_url
    next_cursor = None
    if len(rows) > limit:
        last, key = rows[limit - 1]
        next_cursor = encode_cursor(order, key, last.product.id, mode)
    return ProductPage(
        items=[ProductListItem.from_storefront(r, images[r.product.id], media) for r in page],
        next_cursor=next_cursor,
    )


@public_router.get(
    "/products/{slug}",
    response_model=ProductDetail,
    dependencies=[Depends(_DETAIL_LIMIT)],
    summary="Read one visible product",
    responses=_DETAIL_RESPONSES,
)
async def read_product(slug: str, session: AsyncSession = Depends(get_session)) -> ProductDetail:
    found = (
        await StorefrontProductQuery(session).get_by_slug(slug) if is_canonical_slug(slug) else None
    )
    if found is None:
        raise not_found_error()
    images = await ProductImageRepository(session).live_for_product(found.product.id)
    return ProductDetail.from_storefront(found, images, get_settings().media_public_url)
