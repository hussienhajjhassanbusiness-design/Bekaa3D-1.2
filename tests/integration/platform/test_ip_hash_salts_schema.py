"""`ip_hash_salts` as the migration builds it (VS-046, ADR-028).

Every test that writes rolls back: the table holds the one global current salt."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_exactly_one_current_salt_of_32_bytes_exists(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text("SELECT is_current, octet_length(salt) AS n FROM ip_hash_salts")
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].is_current is True
    assert rows[0].n == 32
    await db_session.rollback()


@pytest.mark.integration
async def test_a_second_current_salt_is_refused_by_the_partial_unique_index(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError, match="uq_ip_hash_salts_one_current"):
        await db_session.execute(
            text("INSERT INTO ip_hash_salts (salt) VALUES (gen_random_bytes(32))")
        )
    await db_session.rollback()


@pytest.mark.integration
async def test_a_non_current_salt_may_coexist_with_the_current_one(
    db_session: AsyncSession,
) -> None:
    """The index is partial: only `is_current` rows are unique."""
    await db_session.execute(
        text("INSERT INTO ip_hash_salts (salt, is_current) VALUES (gen_random_bytes(32), false)")
    )
    count = await db_session.scalar(text("SELECT count(*) FROM ip_hash_salts"))
    assert count == 2
    await db_session.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("length", [0, 31, 33])
async def test_a_salt_that_is_not_32_bytes_violates_the_check(
    db_session: AsyncSession, length: int
) -> None:
    with pytest.raises(IntegrityError, match="ck_ip_hash_salts_salt_length"):
        await db_session.execute(
            text(
                "INSERT INTO ip_hash_salts (salt, is_current) "
                "VALUES (substring(gen_random_bytes(64) FROM 1 FOR :n), false)"
            ),
            {"n": length},
        )
    await db_session.rollback()
