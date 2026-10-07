"""Importing this module registers every context's ORM models onto
Base.metadata. Any entrypoint that touches the database - the API process,
the worker, Alembic - must import this before doing anything with the ORM,
or SQLAlchemy's cross-context foreign-key resolution fails (it doesn't know
about a table whose model class was never imported in that process)."""

import app.catalog.infrastructure.models as _catalog_models  # noqa: F401
import app.engagement.infrastructure.models as _engagement_models  # noqa: F401
import app.identity.infrastructure.models as _identity_models  # noqa: F401
import app.platform.infrastructure.models as _platform_models  # noqa: F401
