"""The rotation rule and use case (VS-046, SEC-25): once per UTC calendar month."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.platform.application.commands.rotate_ip_hash_salt import RotateIpHashSalt
from app.platform.domain.entities import IpHashSalt
from app.platform.domain.ip_hash_rotation import rotation_due

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
MONTH_START = datetime(2026, 10, 1, tzinfo=UTC)


def test_no_salt_is_due() -> None:
    assert rotation_due(None, NOW) is True


def test_the_last_microsecond_of_the_previous_month_is_due() -> None:
    assert rotation_due(MONTH_START - timedelta(microseconds=1), NOW) is True


def test_the_first_instant_of_this_month_is_not_due() -> None:
    assert rotation_due(MONTH_START, NOW) is False


def test_a_non_utc_now_is_normalised_to_the_utc_month() -> None:
    """1 Nov 02:00 at +05:00 is still 31 Oct UTC: an October salt is not due."""
    local = datetime(2026, 11, 1, 2, tzinfo=timezone(timedelta(hours=5)))
    assert rotation_due(datetime(2026, 10, 2, tzinfo=UTC), local) is False
    assert rotation_due(datetime(2026, 9, 30, tzinfo=UTC), local) is True


def test_a_salt_dated_in_the_future_is_not_due() -> None:
    """Clock skew must not make every run rotate."""
    assert rotation_due(NOW + timedelta(days=3), NOW) is False


class _FakeSalts:
    def __init__(self, current: tuple[UUID, datetime] | None) -> None:
        self.current = current
        self.calls: list[str] = []
        self.new_id = uuid4()

    async def lock_rotation(self) -> None:
        self.calls.append("lock")

    async def current_created_at(self) -> tuple[UUID, datetime] | None:
        self.calls.append("read")
        return self.current

    async def replace_current(self) -> UUID:
        self.calls.append("replace")
        return self.new_id

    async def load_current(self) -> IpHashSalt | None:
        raise AssertionError("rotation never reads salt bytes")


class _FakeAudit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **fields: Any) -> None:
        self.rows.append(fields)


async def test_the_lock_is_taken_before_the_age_is_read() -> None:
    salts, audit = _FakeSalts((uuid4(), MONTH_START)), _FakeAudit()
    assert await RotateIpHashSalt(salts, audit).execute(now=NOW) is None
    assert salts.calls == ["lock", "read"]
    assert audit.rows == []


async def test_a_due_rotation_audits_ids_only() -> None:
    old = uuid4()
    salts, audit = _FakeSalts((old, MONTH_START - timedelta(days=1))), _FakeAudit()
    assert await RotateIpHashSalt(salts, audit).execute(now=NOW) == salts.new_id
    assert salts.calls == ["lock", "read", "replace"]
    assert audit.rows == [
        {
            "actor_user_id": None,
            "action": "ip_hash_salt.rotated",
            "entity_type": "IpHashSalt",
            "entity_id": salts.new_id,
            "before_data": {"previous_salt_id": str(old)},
        }
    ]


async def test_an_empty_table_self_heals_with_no_previous_id() -> None:
    salts, audit = _FakeSalts(None), _FakeAudit()
    assert await RotateIpHashSalt(salts, audit).execute(now=NOW) == salts.new_id
    assert audit.rows[0]["before_data"] == {"previous_salt_id": None}
