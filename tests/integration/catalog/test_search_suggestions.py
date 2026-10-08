"""`GET /api/v1/search/suggestions` (VS-016): typo-tolerant name autocomplete, at most
ten, visible products only, a fixed payload and 422 on bad input."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.domain.storefront import MAX_SEARCH_LENGTH, MAX_SUGGESTIONS
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import made_up_word, seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for

SUGGESTIONS = "/api/v1/search/suggestions"

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _suggest(client: TestClient, q: str, **params: Any) -> list[dict[str, Any]]:
    response = client.get(SUGGESTIONS, params={"q": q} | params)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


@pytest.mark.parametrize(
    "typed",
    [
        lambda w: w,
        lambda w: w[:4],
        lambda w: w[:3] + w[4:],
        lambda w: w[:3] + "x" + w[4:],
        lambda w: w.upper(),
    ],
    ids=["exact", "prefix-as-typed", "deletion", "substitution", "case"],
)
async def test_a_partial_or_one_typo_name_is_suggested(
    db_session: AsyncSession, typed: Any
) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, name=f"{word.capitalize()} lamp")
    with client_for(main_app) as client:
        assert [s["id"] for s in _suggest(client, typed(word))] == [str(product.id)]


async def test_a_suggestion_carries_exactly_its_link_fields(db_session: AsyncSession) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, name=word, type=ProductType.STL)
    with client_for(main_app) as client:
        [item] = _suggest(client, word)
    assert item == {"id": str(product.id), "name": word, "slug": product.slug, "type": "stl"}


async def test_the_closest_name_is_suggested_first(db_session: AsyncSession) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    far = await seed_product(db_session, refs, name=f"{word[:-1]}x stand")
    near = await seed_product(db_session, refs, name=f"{word} stand")
    with client_for(main_app) as client:
        assert [s["id"] for s in _suggest(client, word)] == [str(near.id), str(far.id)]


async def test_suggestions_are_capped_at_ten(db_session: AsyncSession) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    for i in range(MAX_SUGGESTIONS + 2):
        await seed_product(db_session, refs, name=f"{word} {i}")
    with client_for(main_app) as client:
        assert len(_suggest(client, word)) == MAX_SUGGESTIONS == 10
        assert len(_suggest(client, word, limit=3)) == 3


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": " a "},
        {"q": "x" * (MAX_SEARCH_LENGTH + 1)},
        {"q": "lamp", "limit": 0},
        {"q": "lamp", "limit": MAX_SUGGESTIONS + 1},
        {"q": "lamp\x07"},
    ],
    ids=["missing", "empty", "one-letter", "too-long", "limit-0", "limit-11", "control"],
)
def test_bad_suggestion_input_is_a_validation_error(params: dict[str, Any]) -> None:
    with client_for(main_app) as client:
        assert_problem(client.get(SUGGESTIONS, params=params), 422, "VALIDATION_ERROR")


def test_suggestions_need_no_account() -> None:
    with client_for(main_app) as client:
        assert not client.cookies
        assert client.get(SUGGESTIONS, params={"q": "lamp"}).status_code == 200
