"""Two `rotate_ip_salt` runs at once (VS-046): the advisory lock lets exactly one rotate."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.jobs.rotate_ip_salt import rotate_ip_salt
from tests.integration.platform.test_rotate_ip_salt import make_due


@pytest.mark.concurrency
@pytest.mark.integration
@pytest.mark.parametrize("workers", [2, 5])
async def test_concurrent_rotations_rotate_exactly_once(
    db_engine: AsyncEngine, workers: int
) -> None:
    old_id = await make_due(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    results = await asyncio.gather(
        *(rotate_ip_salt({"session_factory": factory}) for _ in range(workers)),
        return_exceptions=True,
    )
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert results.count(True) == 1 and results.count(False) == workers - 1

    async with db_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id FROM ip_hash_salts"))).all()
        audits = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'ip_hash_salt.rotated' "
                "AND before_data->>'previous_salt_id' = :id"
            ),
            {"id": str(old_id)},
        )
    assert len(rows) == 1 and rows[0].id != old_id
    assert audits == 1
