"""`GET /api/v1/search/suggestions` (VS-016, docs/storefront-catalogue.md): typo-tolerant
autocomplete over visible product names. Public and rate limited."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.api.product_cursor import bad_query
from app.catalog.api.reference_data import PUBLIC_RATE_WINDOW_SECONDS
from app.catalog.api.search_schemas import SearchSuggestionList, SearchSuggestionRead
from app.catalog.domain.storefront import (
    MAX_SUGGESTIONS,
    search_term,
    suggestion_term_errors,
)
from app.catalog.infrastructure.storefront_query import StorefrontProductQuery
from app.core.rate_limit import rate_limiter

public_router = APIRouter(tags=["catalogue"])

# 5x the public allowance: requests are per keystroke, and carrier-grade NAT puts many
# Lebanese mobile customers behind one IP (ADR-023). Its own counter spares browsing.
SUGGESTIONS_RATE_LIMIT = 3000
_SUGGESTIONS_LIMIT = rate_limiter(
    key_prefix="catalogue:suggestions",
    limit=SUGGESTIONS_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)

_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"description": "VALIDATION_ERROR: bad `q` (needs a 3-letter word) or `limit`."},
    429: {"description": "RATE_LIMITED."},
}


@public_router.get(
    "/search/suggestions",
    response_model=SearchSuggestionList,
    dependencies=[Depends(_SUGGESTIONS_LIMIT)],
    summary="Suggest visible products by name",
    responses=_RESPONSES,
)
async def search_suggestions(
    q: str = Query(description="What the visitor has typed so far; trimmed."),
    limit: int = Query(default=MAX_SUGGESTIONS, ge=1, le=MAX_SUGGESTIONS),
    session: AsyncSession = Depends(get_session),
) -> SearchSuggestionList:
    term = search_term(q) or ""
    if problem := suggestion_term_errors(term):
        raise bad_query("q", problem)
    found = await StorefrontProductQuery(session).suggestions(term, limit)
    return SearchSuggestionList(items=[SearchSuggestionRead.from_domain(s) for s in found])
