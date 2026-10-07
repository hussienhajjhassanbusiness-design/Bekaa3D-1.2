class CatalogDomainError(Exception):
    """Base for catalogue-context domain errors. No HTTP knowledge lives here -
    routers translate these into the SRS-defined stable error codes."""


class ReferenceValueNotFoundError(CatalogDomainError):
    """No category/material/colour exists with this id.

    One error for all three resources, because the API answers all three the
    same way: a 404 that is indistinguishable from the admin boundary's own 404
    for a non-administrator (SEC-10).
    """

    def __init__(self, entity_type: str, entity_id: object) -> None:
        super().__init__(f"No {entity_type} exists with id {entity_id!r}.")
        self.entity_type = entity_type
        self.entity_id = entity_id


class SlugConflictError(CatalogDomainError):
    """Another live row already owns this slug.

    Raised by translating PostgreSQL's unique-violation on the partial index
    rather than by checking first - see `CreateCategory` for why a read-then-
    write check is not the mechanism.
    """

    def __init__(self, slug: str, entity_type: str = "Category") -> None:
        super().__init__(f"The slug {slug!r} is already in use by a live {entity_type.lower()}.")
        self.slug = slug
        self.entity_type = entity_type


class NameConflictError(CatalogDomainError):
    """Another live material/colour already has this name, ignoring case.

    Materials and colours are facet values; "PLA" and "pla" as two live
    materials would split one filter into two (SRS 592). Raised by translating
    the case-insensitive live-name unique index, never by checking first - the
    same reasoning as `SlugConflictError`.
    """

    def __init__(self, entity_type: str, name: str) -> None:
        super().__init__(f"A live {entity_type.lower()} named {name!r} already exists.")
        self.entity_type = entity_type
        self.name = name


class InvalidSlugError(CatalogDomainError):
    """The submitted slug is not a well-formed slug."""

    def __init__(self, slug: str, reason: str) -> None:
        super().__init__(f"Invalid slug {slug!r}: {reason}")
        self.slug = slug
        self.reason = reason


class ArchivedValueNotMutableError(CatalogDomainError):
    """An archived row cannot be changed through the ordinary update endpoint.

    VS-010 ships no restore operation, so archiving is terminal for the normal
    admin surface. The route maps this to the catalogue's existing
    `409 INVALID_STATE_TRANSITION` rather than a new code: "requested
    state-machine transition is illegal" already describes it exactly, and the
    error catalogue is a contract rather than a place to add synonyms.
    """

    def __init__(self, entity_type: str, entity_id: object) -> None:
        super().__init__(f"{entity_type} {entity_id!r} is archived and cannot be modified.")
        self.entity_type = entity_type
        self.entity_id = entity_id


class ReferenceValueInUseError(CatalogDomainError):
    """A live product still uses this category/material/colour, so it cannot be archived."""

    def __init__(self, entity_type: str, entity_id: object) -> None:
        super().__init__(f"{entity_type} {entity_id!r} is used by a live product.")
        self.entity_type = entity_type
        self.entity_id = entity_id


class ReferenceValueUnusableError(CatalogDomainError):
    """A product named a category/material/colour that is unknown or archived."""

    def __init__(self, field: str, entity_id: object) -> None:
        super().__init__(f"{field} {entity_id!r} does not name a live value.")
        self.field = field
        self.entity_id = entity_id


class ProductNotFoundError(CatalogDomainError):
    def __init__(self, product_id: object) -> None:
        super().__init__(f"No product exists with id {product_id!r}.")
        self.product_id = product_id


class ProductValidationError(CatalogDomainError):
    """Field-level rule violations, keyed by field name (type integrity included)."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{field}: {reason}" for field, reason in errors.items()))
        self.errors = errors


class VersionConflictError(CatalogDomainError):
    """The caller's `version` is not the stored one; nothing was written (ADR-020)."""

    def __init__(self, entity_id: object, current_version: int) -> None:
        super().__init__(f"{entity_id!r} is at version {current_version}.")
        self.entity_id = entity_id
        self.current_version = current_version


class ProductImageNotFoundError(CatalogDomainError):
    """No live image with this id belongs to this product (a foreign id is the same 404)."""

    def __init__(self, image_id: object) -> None:
        super().__init__(f"No live product image with id {image_id!r}.")
        self.image_id = image_id


class UploadRejectedError(CatalogDomainError):
    """Size, count or content refused an upload (`422 UPLOAD_REJECTED`)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MalwareDetectedError(CatalogDomainError):
    def __init__(self, signature: str | None) -> None:
        super().__init__(f"Upload failed the malware scan ({signature or 'unnamed'}).")
        self.signature = signature


class ImageOrderMismatchError(CatalogDomainError):
    """A reorder must name every live image of the product exactly once."""


class CoverDeletionBlockedError(CatalogDomainError):
    """The cover cannot go while other live images remain; choose a new cover first."""

    def __init__(self, image_id: object) -> None:
        super().__init__(f"Image {image_id!r} is the cover; set another cover first.")
        self.image_id = image_id
