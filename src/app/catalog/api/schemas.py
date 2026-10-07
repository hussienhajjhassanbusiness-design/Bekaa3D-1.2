from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.catalog.domain.entities import Category, Colour, Material
from app.core.text import reject_control_characters

# 200 characters, matching the longest existing string bound in the project
# (`pickup_hours` in the settings registry). The columns are TEXT and impose no
# limit of their own; this is edge validation, and it is a V1 decision recorded
# in docs/reference-data.md rather than a number the SRS supplies.
MAX_NAME_LENGTH = 200


def _clean_name(value: str) -> str:
    """Trim, and reject a name that is only whitespace.

    Normalisation rather than mere validation: otherwise `" Resin "` and
    `"Resin"` are two different stored values of one material.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("name must not be empty")
    return trimmed


# Control characters are refused before trimming (BUG-03): a NUL used to reach
# PostgreSQL and answer 500. Slugs need no such check - the domain pattern
# admits only [a-z0-9-].
ReferenceName = Annotated[
    str,
    Field(min_length=1, max_length=MAX_NAME_LENGTH),
    AfterValidator(reject_control_characters),
    AfterValidator(_clean_name),
]


# --------------------------------------------------------------------------
# Public
#
# These schemas are the public contract, and their field lists are the second
# guard against leaking operational state. The query already filters to live,
# active rows; even if that filter were wrong, there is no field here for
# `is_active`, `deleted_at`, `created_at` or `updated_at` to land in.
# --------------------------------------------------------------------------


class CategoryRead(BaseModel):
    id: UUID
    name: str
    slug: str

    @classmethod
    def from_entity(cls, category: Category) -> "CategoryRead":
        return cls(id=category.id, name=category.name, slug=category.slug)


class CategoryList(BaseModel):
    """A hard-limited reference list (api-endpoints.md 227). Not a cursor page -
    there is deliberately no `next_cursor`, because the contract is a bounded
    list rather than pagination."""

    items: list[CategoryRead]


class MaterialRead(BaseModel):
    id: UUID
    name: str

    @classmethod
    def from_entity(cls, material: Material) -> "MaterialRead":
        return cls(id=material.id, name=material.name)


class MaterialList(BaseModel):
    items: list[MaterialRead]


class ColourRead(BaseModel):
    id: UUID
    name: str

    @classmethod
    def from_entity(cls, colour: Colour) -> "ColourRead":
        return cls(id=colour.id, name=colour.name)


class ColourList(BaseModel):
    items: list[ColourRead]


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    """api-endpoints.md 29.12."""

    model_config = ConfigDict(extra="forbid")

    name: ReferenceName
    # Validated and normalised by the domain, not here: the rules live in
    # `catalog.domain.slug` so the API and any future importer share one
    # definition of what a slug is.
    slug: str = Field(min_length=1, max_length=200)
    is_active: bool = True


class _RejectEmptyPatch(BaseModel):
    """A PATCH that sets nothing is a client bug, not a no-op.

    Distinct from a PATCH that submits the values already stored - that one is a
    legitimate request which this project audits with equal before/after
    (the VS-007 convention). This rejects a body with no fields at all, which
    can only mean the caller built the request wrongly.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("at least one field must be provided")
        return self


class CategoryUpdate(_RejectEmptyPatch):
    name: ReferenceName | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class MaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ReferenceName
    is_active: bool = True


class MaterialUpdate(_RejectEmptyPatch):
    name: ReferenceName | None = None
    is_active: bool | None = None


class ColourCreate(MaterialCreate):
    """Identical to MaterialCreate; named separately because it is a distinct
    part of the public API contract and should not silently change if one of
    them gains a field."""


class ColourUpdate(_RejectEmptyPatch):
    name: ReferenceName | None = None
    is_active: bool | None = None


class CategoryDetail(BaseModel):
    """Admin read. Unlike the public schema this *does* carry lifecycle state -
    an administrator needs to see whether a row is disabled or archived."""

    id: UUID
    name: str
    slug: str
    is_active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, category: Category) -> "CategoryDetail":
        return cls(
            id=category.id,
            name=category.name,
            slug=category.slug,
            is_active=category.is_active,
            deleted_at=category.deleted_at,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )


class MaterialDetail(BaseModel):
    id: UUID
    name: str
    is_active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, value: Material | Colour) -> Self:
        # `Self` rather than `MaterialDetail`, because ColourDetail subclasses
        # this and must return its own type.
        return cls(
            id=value.id,
            name=value.name,
            is_active=value.is_active,
            deleted_at=value.deleted_at,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )


class ColourDetail(MaterialDetail):
    """Same fields; separate name so the two contracts can diverge later."""


class AdminCategoryPage(BaseModel):
    items: list[CategoryDetail]
    next_cursor: str | None


class AdminMaterialPage(BaseModel):
    items: list[MaterialDetail]
    next_cursor: str | None


class AdminColourPage(BaseModel):
    items: list[ColourDetail]
    next_cursor: str | None
