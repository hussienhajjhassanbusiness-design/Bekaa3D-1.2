from datetime import datetime
from uuid import UUID

from app.platform.application.ports import AuditWriter, IpHashSaltStore
from app.platform.domain.ip_hash_rotation import rotation_due


class RotateIpHashSalt:
    """Replace the IP-hash salt once per UTC month (SEC-25, ADR-028).
    The caller owns the transaction: lock, swap and audit row commit or roll back together."""

    def __init__(self, salts: IpHashSaltStore, audit: AuditWriter) -> None:
        self._salts = salts
        self._audit = audit

    async def execute(self, *, now: datetime) -> UUID | None:
        """The new salt's id, or None when the current salt is from this month."""
        await self._salts.lock_rotation()
        current = await self._salts.current_created_at()
        if not rotation_due(current[1] if current else None, now):
            return None
        new_id = await self._salts.replace_current()
        await self._audit.record(
            actor_user_id=None,
            action="ip_hash_salt.rotated",
            entity_type="IpHashSalt",
            entity_id=new_id,
            before_data={"previous_salt_id": str(current[0]) if current else None},
        )
        return new_id
