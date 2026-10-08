"""The public product and suggestion routes are rate limited per IP, each with its own
counter (VS-015, VS-016)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.api.reference_data import PUBLIC_RATE_LIMIT
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, fresh_ip


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("route", ["list", "detail", "suggestions"])
async def test_each_route_refuses_past_its_limit_and_leaves_the_other_open(
    db_session: AsyncSession, route: str
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    paths = {
        "list": f"/api/v1/products?category_id={refs.category.id}",
        "detail": f"/api/v1/products/{product.slug}",
        "suggestions": "/api/v1/search/suggestions?q=lamp",
    }
    others = [path for name, path in paths.items() if name != route]
    with client_for(main_app, ip=fresh_ip()) as client:
        allowed = [client.get(paths[route]) for _ in range(PUBLIC_RATE_LIMIT)]
        refused = client.get(paths[route])
        still_open = [client.get(path) for path in others]
    assert {r.status_code for r in allowed} == {200}
    assert allowed[-1].headers["RateLimit-Remaining"] == "0"
    assert_problem(refused, 429, "RATE_LIMITED")
    assert int(refused.headers["Retry-After"]) > 0
    assert [r.status_code for r in still_open] == [200, 200]
