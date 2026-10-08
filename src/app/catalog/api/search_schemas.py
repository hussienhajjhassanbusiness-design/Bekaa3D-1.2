"""`SearchSuggestionList` (VS-016): just enough to label a suggestion and link to it."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel

from app.catalog.domain.enums import ProductType
from app.catalog.domain.storefront import SearchSuggestion


class SearchSuggestionRead(BaseModel):
    id: UUID
    name: str
    slug: str
    type: ProductType

    @classmethod
    def from_domain(cls, suggestion: SearchSuggestion) -> Self:
        return cls(
            id=suggestion.id, name=suggestion.name, slug=suggestion.slug, type=suggestion.type
        )


class SearchSuggestionList(BaseModel):
    items: list[SearchSuggestionRead]
