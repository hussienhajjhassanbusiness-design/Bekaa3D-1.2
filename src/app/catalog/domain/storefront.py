"""The public catalogue's read side (VS-015, docs/storefront-catalogue.md)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.exceptions import ProductValidationError
from app.catalog.domain.product import Product
from app.core.text import CONTROL_CHARACTER_MESSAGE, has_control_characters

StorefrontSort = Literal["price", "-price", "-average_rating", "-created_at", "-relevance"]
DEFAULT_SORT: StorefrontSort = "-created_at"
RELEVANCE_SORT: StorefrontSort = "-relevance"
MAX_RATING = Decimal(5)
# `average_rating` is NUMERIC(3,2): a finer bound would be rounded by PostgreSQL.
RATING_STEP = Decimal("0.01")
CursorKey = int | Decimal | datetime | float

# The admin list's bound (VS-013). Trigrams need three characters to narrow anything.
MAX_SEARCH_LENGTH = 200
MIN_FUZZY_LENGTH = 3
MIN_SUGGESTION_LENGTH = MIN_FUZZY_LENGTH
MAX_SUGGESTIONS = 10
# SRS 6.3: below this many full-text hits, trigram matches on the name join in.
MIN_FULL_TEXT_HITS = 5


class SearchMode(StrEnum):
    FULL_TEXT = "full_text"
    FUZZY = "fuzzy"


def fuzzy_eligible(term: str, *, excludes_words: bool) -> bool:
    """ADR-023: shorter terms match every name, and trigrams ignore `-word`."""
    return len(term) >= MIN_FUZZY_LENGTH and not excludes_words


def search_mode_for(full_text_hits: int, *, eligible: bool) -> SearchMode:
    fuzzy = eligible and full_text_hits < MIN_FULL_TEXT_HITS
    return SearchMode.FUZZY if fuzzy else SearchMode.FULL_TEXT


def search_term(raw: str | None) -> str | None:
    """Trimmed; a blank search box means no search at all."""
    term = raw.strip() if raw is not None else ""
    return term or None


def search_term_errors(term: str, *, min_length: int = 1) -> str | None:
    if has_control_characters(term):
        return CONTROL_CHARACTER_MESSAGE
    if not min_length <= len(term) <= MAX_SEARCH_LENGTH:
        return f"must be {min_length} to {MAX_SEARCH_LENGTH} characters"
    return None


def resolve_sort(sort: StorefrontSort | None, q: str | None) -> StorefrontSort:
    """Relevance is the default with a search and meaningless without one (ADR-023)."""
    if sort == RELEVANCE_SORT and q is None:
        raise ProductValidationError({"sort": "-relevance needs a search term (q)"})
    return sort or (RELEVANCE_SORT if q is not None else DEFAULT_SORT)


_ONLINE_MODES = frozenset({PurchaseMode.ONLINE_ONLY, PurchaseMode.BOTH})
_WHATSAPP_MODES = frozenset({PurchaseMode.WHATSAPP_ONLY, PurchaseMode.BOTH})


@dataclass(frozen=True)
class StorefrontFilter:
    """The api-endpoints.md 31 allowlist; `q` is already trimmed. Every facet ANDs."""

    product_type: ProductType | None = None
    category_id: UUID | None = None
    material_id: UUID | None = None
    colour_id: UUID | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    min_rating: Decimal | None = None
    featured: bool | None = None
    q: str | None = None

    def __post_init__(self) -> None:
        errors: dict[str, str] = {}
        if self.q is not None and (problem := search_term_errors(self.q)):
            errors["q"] = problem
        elif self.q is not None and self.q != self.q.strip():
            errors["q"] = "must be trimmed"
        low, high = self.price_min_cents, self.price_max_cents
        if low is not None and high is not None and low > high:
            errors["price_min_cents"] = "must not exceed price_max_cents"
        rating = self.min_rating
        if rating is not None and not 0 <= rating <= MAX_RATING:
            errors["min_rating"] = f"must be between 0 and {MAX_RATING}"
        elif rating is not None and rating != rating.quantize(RATING_STEP):
            errors["min_rating"] = "must have at most 2 decimal places"
        if errors:
            raise ProductValidationError(errors)


@dataclass(frozen=True)
class CategoryRef:
    id: UUID
    name: str
    slug: str


@dataclass(frozen=True)
class FacetRef:
    id: UUID
    name: str


@dataclass(frozen=True)
class CommerceCapabilities:
    can_add_to_cart: bool
    can_offer: bool
    whatsapp_available: bool


def capabilities(
    product_type: ProductType, purchase_mode: PurchaseMode | None, is_available: bool
) -> CommerceCapabilities:
    """Product state only; per-customer checks (STL already owned) stay with the cart."""
    physical = product_type is ProductType.PHYSICAL
    return CommerceCapabilities(
        can_add_to_cart=is_available and (not physical or purchase_mode in _ONLINE_MODES),
        can_offer=is_available and not physical,
        whatsapp_available=physical and purchase_mode in _WHATSAPP_MODES,
    )


@dataclass(frozen=True)
class StorefrontProduct:
    """A visible product with the reference names a storefront page shows."""

    product: Product
    category: CategoryRef
    material: FacetRef | None
    colour: FacetRef | None

    @property
    def capabilities(self) -> CommerceCapabilities:
        a = self.product.attributes
        return capabilities(self.product.type, a.purchase_mode, a.is_available)


@dataclass(frozen=True)
class SearchSuggestion:
    id: UUID
    name: str
    slug: str
    type: ProductType
