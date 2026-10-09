"""`GET /api/v1/products?q=` (VS-016): full text first, trigram fallback below five hits,
relevance order, facets, visibility, injection and validation. Each test owns its
category or a made-up word, so other tests' products never decide an assertion."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.api.product_cursor import encode_cursor
from app.catalog.domain.enums import ProductType
from app.catalog.domain.storefront import MAX_SEARCH_LENGTH, SearchMode
from app.catalog.infrastructure.models import ProductModel
from app.catalog.infrastructure.storefront_query import (
    WORD_SIMILARITY_THRESHOLD,
    trigram_threshold_statement,
)
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import made_up_word, seed_product, seed_refs
from tests.integration.catalog.test_storefront_products import INVISIBLE, _hide
from tests.integration.deep_support import assert_problem, client_for

PRODUCTS = "/api/v1/products"
SUGGESTIONS = "/api/v1/search/suggestions"

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _search(client: TestClient, q: str, **params: Any) -> list[str]:
    response = client.get(PRODUCTS, params={"q": q, "limit": 100} | params)
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def _top_id() -> uuid.UUID:
    """Higher than any random id, so a tie under `id DESC` lists this row first."""
    return uuid.UUID(f"ffffffff-ffff-4fff-bfff-{uuid.uuid4().hex[:12]}")


async def _similarity(db: AsyncSession, q: str, name: str) -> float:
    query = select(func.word_similarity(q, name))
    return float((await db.execute(query)).scalar_one())


def _walk(client: TestClient, limit: int, **params: Any) -> list[str]:
    seen: list[str] = []
    cursor = None
    for _ in range(50):
        query = params | {"limit": limit} | ({"cursor": cursor} if cursor else {})
        response = client.get(PRODUCTS, params=query)
        assert response.status_code == 200, response.text
        seen += [item["id"] for item in response.json()["items"]]
        cursor = response.json()["next_cursor"]
        if cursor is None:
            return seen
    pytest.fail("pagination never ended")


# ---------------------------------------------------------------- matching


@pytest.mark.parametrize("q", ["dragon", "Dragon", "dragons", "articulating", "DRAGON  "])
async def test_exact_and_stemmed_queries_match(db_session: AsyncSession, q: str) -> None:
    refs = await seed_refs(db_session)
    dragon = await seed_product(db_session, refs, name="Articulated Dragon")
    await seed_product(db_session, refs, name="Spiral Vase")
    with client_for(main_app) as client:
        assert _search(client, q, category_id=str(refs.category.id)) == [str(dragon.id)]


async def test_descriptions_are_searched_too(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    vase = await seed_product(db_session, refs, name="Vase", description="Hand-painted resin")
    with client_for(main_app) as client:
        assert _search(client, "painting", category_id=str(refs.category.id)) == [str(vase.id)]


# `plnter` scores 0.5: it fails under pg_trgm's default 0.6, so it pins ADR-023's threshold.
ONE_TYPO = {
    "deletion": ("dragn", "Articulated Dragon"),
    "substitution": ("dragom", "Articulated Dragon"),
    "insertion": ("draggon", "Articulated Dragon"),
    "multi-word": ("articulatd dragon", "Articulated Dragon"),
    "at-threshold": ("plnter", "Self-watering Planter"),
}


@pytest.mark.parametrize(("q", "name"), ONE_TYPO.values(), ids=ONE_TYPO.keys())
async def test_one_typo_finds_the_product(db_session: AsyncSession, q: str, name: str) -> None:
    refs = await seed_refs(db_session)
    wanted = await seed_product(db_session, refs, name=name)
    await seed_product(db_session, refs, name="Spiral Vase")
    with client_for(main_app) as client:
        assert _search(client, q, category_id=str(refs.category.id)) == [str(wanted.id)]


async def test_a_name_match_ranks_above_a_description_match_above_a_near_miss(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    near = await seed_product(db_session, refs, name="Dragonfly Earrings")
    # The top id: if the A/B weights stopped counting, the tie would list this one first.
    described = await seed_product(
        db_session,
        refs,
        name="Table Lamp",
        description="A dragon coils round the base",
        id=_top_id(),
    )
    named = await seed_product(db_session, refs, name="Dragon Lamp")
    with client_for(main_app) as client:
        ranked = _search(client, "dragon", category_id=str(refs.category.id))
        explicit = _search(client, "dragon", category_id=str(refs.category.id), sort="-relevance")
    assert ranked == explicit == [str(named.id), str(described.id), str(near.id)]


async def test_trigram_matches_join_in_only_below_five_full_text_hits(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    lamps = [await seed_product(db_session, refs, name=f"Moon Lamp {i}") for i in range(5)]
    shade = await seed_product(db_session, refs, name="Lampshade")
    category = str(refs.category.id)
    with client_for(main_app) as client:
        assert set(_search(client, "lamp", category_id=category)) == {str(p.id) for p in lamps}
        await _hide(db_session, refs, lamps[0], "hidden")
        thin = _search(client, "lamp", category_id=category)
    assert set(thin) == {str(p.id) for p in lamps[1:]} | {str(shade.id)}
    assert thin[-1] == str(shade.id), "full-text hits rank above the trigram-only one"


async def test_the_fallback_counts_only_hits_inside_the_facets(db_session: AsyncSession) -> None:
    here, elsewhere = await seed_refs(db_session), await seed_refs(db_session)
    for _ in range(5):
        await seed_product(db_session, elsewhere, name="Moon Lamp")
    lamps = [await seed_product(db_session, here, name="Moon Lamp") for _ in range(2)]
    shade = await seed_product(db_session, here, name="Lampshade")
    with client_for(main_app) as client:
        found = _search(client, "lamp", category_id=str(here.category.id))
    assert set(found) == {str(p.id) for p in [*lamps, shade]}, "2 hits here, not 7 site-wide"


@pytest.mark.parametrize("q", ["lamp -moon", "lamp - moon", "-moon lamp", "-moon"])
async def test_an_excluded_word_never_comes_back(db_session: AsyncSession, q: str) -> None:
    refs = await seed_refs(db_session)
    await seed_product(db_session, refs, name="Moon Lamp")
    vases = [await seed_product(db_session, refs, name="Spiral Vase") for _ in range(2)]
    with client_for(main_app) as client:
        found = _search(client, q, category_id=str(refs.category.id))
    # Under five hits, yet no trigram fallback: it would match "Moon Lamp" on both words.
    expected = {str(p.id) for p in vases} if q == "-moon" else set()
    assert set(found) == expected


@pytest.mark.parametrize(
    ("q", "found"),
    [("s", False), ("sp", False), ("s s", False), ("(s)", False), ("s!!", False), ("spi", True)],
)
async def test_typo_matching_needs_a_word_of_three_letters(
    db_session: AsyncSession, q: str, found: bool
) -> None:
    refs = await seed_refs(db_session)
    vase = await seed_product(db_session, refs, name="Spiral Vase")
    with client_for(main_app) as client:
        result = _search(client, q, category_id=str(refs.category.id))
    assert result == ([str(vase.id)] if found else [])


async def test_trigram_only_hits_are_ordered_by_similarity(db_session: AsyncSession) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    # Typos in the middle, so no stem matches `word`: both rows are trigram-only.
    near_name, far_name = word[:8] + "x" + word[9:], word[:4] + "x" + word[5:]
    near = await seed_product(db_session, refs, name=near_name)
    far = await seed_product(db_session, refs, name=far_name, id=_top_id())
    near_score = await _similarity(db_session, word, near_name)
    far_score = await _similarity(db_session, word, far_name)
    assert near_score > far_score >= WORD_SIMILARITY_THRESHOLD
    with client_for(main_app) as client:
        assert _search(client, word, category_id=str(refs.category.id)) == [
            str(near.id),
            str(far.id),
        ]


async def test_a_name_below_the_threshold_is_not_a_typo_match(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    vase = await seed_product(db_session, refs, name="Spiral Vase")
    await seed_product(db_session, refs, name="Base Plate")
    # 0.40: a looser threshold such as 0.3 would let it in.
    assert 0.3 <= await _similarity(db_session, "vase", "Base Plate") < WORD_SIMILARITY_THRESHOLD
    with client_for(main_app) as client:
        assert _search(client, "vase", category_id=str(refs.category.id)) == [str(vase.id)]


async def test_the_trigram_threshold_ends_with_its_transaction(db_engine: AsyncEngine) -> None:
    show = text("SELECT current_setting('pg_trgm.word_similarity_threshold')")
    async with db_engine.connect() as conn:
        before: str = (await conn.execute(show)).scalar_one()
        await conn.commit()
        await conn.execute(trigram_threshold_statement())
        assert (await conn.execute(show)).scalar_one() == str(WORD_SIMILARITY_THRESHOLD)
        await conn.commit()
        assert (await conn.execute(show)).scalar_one() == before != "0.5"


async def test_search_combines_with_facets(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    wanted = await seed_product(db_session, refs, name="Dragon Lamp", price_cents=900)
    await seed_product(db_session, refs, name="Dragon Lamp", material_id=refs.materials[1].id)
    await seed_product(db_session, refs, name="Dragon Lamp", price_cents=5000)
    await seed_product(db_session, refs, name="Dragon", type=ProductType.STL)
    await seed_product(db_session, refs, name="Moon Lamp", price_cents=900)
    params = {
        "category_id": str(refs.category.id),
        "type": "physical",
        "material_id": str(refs.materials[0].id),
        "price_max_cents": 1000,
    }
    with client_for(main_app) as client:
        assert _search(client, "dragon", **params) == [str(wanted.id)]
        assert _search(client, "dragn", **params) == [str(wanted.id)]


@pytest.mark.parametrize("how", INVISIBLE)
@pytest.mark.parametrize("mode", list(SearchMode))
async def test_search_never_returns_invisible_products(
    db_session: AsyncSession, how: str, mode: SearchMode
) -> None:
    word = made_up_word()
    gone_refs, kept_refs = await seed_refs(db_session), await seed_refs(db_session)
    gone = await seed_product(db_session, gone_refs, name=f"{word} lamp")
    # Five visible full-text hits keep the first case out of the fallback.
    count = 5 if mode is SearchMode.FULL_TEXT else 1
    kept = [await seed_product(db_session, kept_refs, name=f"{word} vase") for _ in range(count)]
    await _hide(db_session, gone_refs, gone, how)
    q = word if mode is SearchMode.FULL_TEXT else word[:4] + word[5:]
    with client_for(main_app) as client:
        found = _search(client, q)
        suggested = client.get(SUGGESTIONS, params={"q": q}).json()["items"]
    expected = {str(p.id) for p in kept}
    assert set(found) == expected, "the control products must show, or this proves nothing"
    assert {s["id"] for s in suggested} == expected


async def test_search_pages_through_every_match_exactly_once(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    rows = [await seed_product(db_session, refs, name="Lamp", price_cents=100) for _ in range(3)]
    rows += [
        await seed_product(db_session, refs, name=f"Lampshade {i}", price_cents=100 * i)
        for i in range(4)
    ]
    expected = {str(p.id) for p in rows}
    params = {"category_id": str(refs.category.id), "q": "lamp"}
    with client_for(main_app) as client:
        for sort in ("-relevance", "price", "-price", "-created_at", "-average_rating"):
            whole = _search(client, "lamp", category_id=params["category_id"], sort=sort)
            walked = _walk(client, 2, **params, sort=sort)
            assert walked == whole, sort
            assert set(walked) == expected, sort


async def test_a_blank_search_is_a_plain_browse(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    rows = [await seed_product(db_session, refs, name=n) for n in ("Lamp", "Vase")]
    with client_for(main_app) as client:
        found = _search(client, "   ", category_id=str(refs.category.id))
    assert found == [str(rows[1].id), str(rows[0].id)]


# ---------------------------------------------------------------- hostile input

INJECTIONS = [
    "' OR '1'='1",
    "'; DROP TABLE products; --",
    "lamp') OR 1=1 --",
    "' UNION SELECT password_hash FROM users --",
    '"unbalanced',
    "%",
    "_",
    "\\",
    ":*",
    "!&|<->()",
    "lamp:*B",
    "$1",
]


@pytest.mark.parametrize("q", INJECTIONS)
async def test_injection_strings_are_inert(db_session: AsyncSession, q: str) -> None:
    refs = await seed_refs(db_session)
    await seed_product(db_session, refs, name="Vase")
    before = (await db_session.execute(select(func.count()).select_from(ProductModel))).scalar()
    with client_for(main_app) as client:
        found = _search(client, q, category_id=str(refs.category.id))
        suggested = client.get(SUGGESTIONS, params={"q": f"{q} xqz"})
    assert found == [], "a quote or operator must never widen the match"
    assert suggested.status_code == 200, suggested.text
    after = (await db_session.execute(select(func.count()).select_from(ProductModel))).scalar()
    assert after == before


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"q": "x" * (MAX_SEARCH_LENGTH + 1)}, "q"),
        ({"q": "lamp\x00"}, "q"),
        ({"sort": "-relevance"}, "sort"),
        ({"sort": "-relevance", "q": "   "}, "sort"),
        ({"sort": "-relevance", "q": "lamp", "cursor": "garbage"}, "cursor"),
        (
            {"q": "lamp", "sort": "price", "cursor": encode_cursor("price", 1, uuid.uuid4())},
            "cursor",
        ),
        (
            {
                "sort": "price",
                "cursor": encode_cursor("price", 1, uuid.uuid4(), SearchMode.FUZZY),
            },
            "cursor",
        ),
        (
            {"q": "lamp", "cursor": encode_cursor("price", 1, uuid.uuid4(), SearchMode.FUZZY)},
            "cursor",
        ),
        (
            {
                "q": "lamp",
                "cursor": encode_cursor("-relevance", float("nan"), uuid.uuid4(), SearchMode.FUZZY),
            },
            "cursor",
        ),
        # A forged fuzzy cursor cannot reopen the fallback the first page refuses.
        *(
            (
                {
                    "q": q,
                    "cursor": encode_cursor("-relevance", 0.5, uuid.uuid4(), SearchMode.FUZZY),
                },
                "cursor",
            )
            for q in ("sp", "lamp -moon")
        ),
    ],
)
def test_bad_search_input_is_a_validation_error(params: dict[str, Any], field: str) -> None:
    with client_for(main_app) as client:
        response = client.get(PRODUCTS, params=params)
    assert_problem(response, 422, "VALIDATION_ERROR")
    if field != "q" or "\x00" not in params["q"]:
        assert ["query", field] in [e["loc"] for e in response.json()["errors"]]


async def test_the_maximum_length_search_is_accepted(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    await seed_product(db_session, refs)
    with client_for(main_app) as client:
        assert _search(client, "x" * MAX_SEARCH_LENGTH, category_id=str(refs.category.id)) == []


async def test_hiding_a_product_drops_it_from_search_and_suggestions(
    db_session: AsyncSession,
) -> None:
    word = made_up_word()
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, name=f"{word} lamp")

    def suggested(client: TestClient) -> list[str]:
        return [s["id"] for s in client.get(SUGGESTIONS, params={"q": word}).json()["items"]]

    with client_for(main_app) as client:
        assert _search(client, word) == suggested(client) == [str(product.id)]
        await db_session.execute(
            update(ProductModel).where(ProductModel.id == product.id).values(is_visible=False)
        )
        await db_session.commit()
        assert _search(client, word) == suggested(client) == []
