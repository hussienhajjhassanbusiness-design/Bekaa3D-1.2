from sqlalchemy import ColumnElement, and_

from app.catalog.infrastructure.models import CategoryModel, ProductModel


def listed_predicate() -> ColumnElement[bool]:
    """SRS 6.5 storefront visibility; needs `categories` joined. The one definition,
    used by the storefront (VS-015) and the cart reader (VS-022). Bare `is_visible`,
    not `IS TRUE`, so the planner matches the partial indexes."""
    return and_(
        ProductModel.deleted_at.is_(None),
        ProductModel.is_visible.expression,
        CategoryModel.deleted_at.is_(None),
        CategoryModel.is_active.expression,
    )
