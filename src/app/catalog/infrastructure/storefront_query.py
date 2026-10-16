import re
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Double,
    Select,
    Text,
    case,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
    tuple_,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.catalog.domain.enums import ProductType
from app.catalog.domain.storefront import (
    MIN_FULL_TEXT_HITS,
    CategoryRef,
    CursorKey,
    FacetRef,
    SearchMode,
    SearchSuggestion,
    StorefrontFilter,
    StorefrontProduct,
    StorefrontSort,
)
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.product_repository import _to_domain
from app.catalog.infrastructure.visibility import listed_predicate

_Page = Select[ProductModel, CategoryModel, MaterialModel, ColourModel]
_KeyedPage = Select[ProductModel, CategoryModel, MaterialModel, ColourModel, Any]
SORT_COLUMNS: dict[StorefrontSort, Any] = {
    "price": ProductModel.price_cents,
    "-price": ProductModel.price_cents,
    "-average_rating": ProductModel.average_rating,
    "-created_at": ProductModel.created_at,
}

# Measured on PG16: 0.5 admits one deleted, substituted or inserted letter (ADR-023).
WORD_SIMILARITY_THRESHOLD = 0.5
_ENGLISH: ColumnElement[Any] = literal_column("'english'::regconfig")
# A quoted lexeme in tsquery text, with '' as an escaped quote.
_LEXEME = re.compile(r"'(?:[^']|'')*'")


def _base() -> _Page:
    return (
        select(ProductModel, CategoryModel, MaterialModel, ColourModel)
        .join(CategoryModel, CategoryModel.id == ProductModel.category_id)
        .outerjoin(MaterialModel, MaterialModel.id == ProductModel.material_id)
        .outerjoin(ColourModel, ColourModel.id == ProductModel.colour_id)
        .where(listed_predicate())
        .options(defer(ProductModel.search_vector))
    )


def _term(term: str) -> ColumnElement[str]:
    return literal(term, Text)


def _tsquery(term: str) -> ColumnElement[Any]:
    return func.websearch_to_tsquery(_ENGLISH, _term(term))


def _full_text(term: str) -> ColumnElement[bool]:
    return ProductModel.search_vector.op("@@")(_tsquery(term))


def _fuzzy(term: str) -> ColumnElement[bool]:
    """`word_similarity(term, name) >= the session threshold`, served by the trigram index."""
    return _term(term).op("<%")(ProductModel.name)


def relevance(term: str) -> ColumnElement[float]:
    """Full-text hits (2 + ts_rank, which may be 0) rank above trigram-only ones (at most 1);
    name (A) outweighs description (B)."""
    rank = func.ts_rank(ProductModel.search_vector, _tsquery(term))
    score = case(
        (_full_text(term), 2 + rank), else_=func.word_similarity(_term(term), ProductModel.name)
    )
    return cast(score, Double)


def _matches(term: str, mode: SearchMode) -> ColumnElement[bool]:
    return _full_text(term) if mode is SearchMode.FULL_TEXT else or_(_full_text(term), _fuzzy(term))


def _conditions(filters: StorefrontFilter, mode: SearchMode) -> list[ColumnElement[bool]]:
    exact = {
        ProductModel.type: filters.product_type,
        ProductModel.category_id: filters.category_id,
        ProductModel.material_id: filters.material_id,
        ProductModel.colour_id: filters.colour_id,
        ProductModel.is_featured: filters.featured,
    }
    where = [column == value for column, value in exact.items() if value is not None]
    if filters.price_min_cents is not None:
        where.append(ProductModel.price_cents >= filters.price_min_cents)
    if filters.price_max_cents is not None:
        where.append(ProductModel.price_cents <= filters.price_max_cents)
    if filters.min_rating is not None:
        where.append(ProductModel.average_rating >= filters.min_rating)
    if filters.q is not None:
        where.append(_matches(filters.q, mode))
    return where


def _to_storefront(
    row: tuple[ProductModel, CategoryModel, MaterialModel, ColourModel],
) -> StorefrontProduct:
    product, category, material, colour = row
    return StorefrontProduct(
        product=_to_domain(product),
        category=CategoryRef(category.id, category.name, category.slug),
        material=FacetRef(material.id, material.name) if material else None,
        colour=FacetRef(colour.id, colour.name) if colour else None,
    )


def _sort_expression(sort: StorefrontSort, q: str | None) -> Any:
    if sort == "-relevance":
        if q is None:
            raise ValueError("-relevance needs a search term")
        return relevance(q)
    return SORT_COLUMNS[sort]


def page_statement(
    *,
    limit: int,
    sort: StorefrontSort,
    filters: StorefrontFilter,
    mode: SearchMode = SearchMode.FULL_TEXT,
    after: tuple[CursorKey, UUID] | None = None,
) -> _KeyedPage:
    """Keyset page tie-broken by `id`, so inserts never duplicate or skip a row. Each row
    carries its sort key last. `mode` only matters when `filters.q` is set."""
    column = _sort_expression(sort, filters.q)
    stmt = _base().where(*_conditions(filters, mode)).add_columns(column)
    descending = sort.startswith("-")
    if after is not None:
        key, after_id = after
        pair = tuple_(column, ProductModel.id)
        bound = tuple_(literal(key, column.type), literal(after_id, postgresql.UUID(as_uuid=True)))
        # The redundant single-column bound is one the browse indexes can seek on.
        if descending:
            stmt = stmt.where(column <= key, pair < bound)
        else:
            stmt = stmt.where(column >= key, pair > bound)
    order = (column.desc(), ProductModel.id.desc()) if descending else (column, ProductModel.id)
    return stmt.order_by(*order).limit(limit)


def full_text_hits_statement(filters: StorefrontFilter) -> Select[int]:
    """How many visible products match in full text, counted only up to the threshold."""
    hits = (
        select(ProductModel.id)
        .join(CategoryModel, CategoryModel.id == ProductModel.category_id)
        .where(listed_predicate(), *_conditions(filters, SearchMode.FULL_TEXT))
    )
    return select(func.count()).select_from(hits.limit(MIN_FULL_TEXT_HITS).subquery())


def excludes_words_statement(term: str) -> Select[str]:
    return select(cast(_tsquery(term), Text))


def tsquery_negates(tsquery_text: str) -> bool:
    """PostgreSQL's own parse decides what `-word` means (`lamp - moon` negates too)."""
    return "!" in _LEXEME.sub("", tsquery_text)


def suggestions_statement(term: str, limit: int) -> Select[UUID, str, str, ProductType]:
    stmt = (
        select(ProductModel.id, ProductModel.name, ProductModel.slug, ProductModel.type)
        .join(CategoryModel, CategoryModel.id == ProductModel.category_id)
        .where(listed_predicate(), _fuzzy(term))
    )
    score = func.word_similarity(_term(term), ProductModel.name)
    return stmt.order_by(score.desc(), ProductModel.name, ProductModel.id).limit(limit)


def trigram_threshold_statement() -> Select[str]:
    """Transaction-local, so it never leaks to another request on a pooled connection."""
    setting = "pg_trgm.word_similarity_threshold"
    return select(func.set_config(setting, str(WORD_SIMILARITY_THRESHOLD), True))


class StorefrontProductQuery:
    """Read-only: the storefront never writes, so it takes no locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def full_text_hits(self, filters: StorefrontFilter) -> int:
        return int((await self._session.execute(full_text_hits_statement(filters))).scalar_one())

    async def excludes_words(self, term: str) -> bool:
        return tsquery_negates(
            (await self._session.execute(excludes_words_statement(term))).scalar_one()
        )

    async def list_page(
        self,
        *,
        limit: int,
        sort: StorefrontSort,
        filters: StorefrontFilter,
        mode: SearchMode = SearchMode.FULL_TEXT,
        after: tuple[CursorKey, UUID] | None = None,
    ) -> list[tuple[StorefrontProduct, CursorKey]]:
        if filters.q is not None and mode is SearchMode.FUZZY:
            await self._session.execute(trigram_threshold_statement())
        stmt = page_statement(limit=limit, sort=sort, filters=filters, mode=mode, after=after)
        rows = (await self._session.execute(stmt)).all()
        return [(_to_storefront((p, c, m, k)), key) for p, c, m, k, key in rows]

    async def suggestions(self, term: str, limit: int) -> list[SearchSuggestion]:
        await self._session.execute(trigram_threshold_statement())
        rows = (await self._session.execute(suggestions_statement(term, limit))).all()
        return [SearchSuggestion(r.id, r.name, r.slug, r.type) for r in rows]

    async def get_by_slug(self, slug: str) -> StorefrontProduct | None:
        stmt = _base().where(ProductModel.slug == slug)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        product, category, material, colour = row
        return _to_storefront((product, category, material, colour))
