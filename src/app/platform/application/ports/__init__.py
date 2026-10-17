"""Platform's ports: the interfaces its application layer and other contexts code against.

Pure `Protocol`s, one module per port - no SQLAlchemy, no infrastructure import - so the application
layer depends on these alone (CLAUDE.md, architecture rules; BUG-41). The
concrete adapters live in `app.platform.infrastructure`, and other contexts
obtain them only through `app.platform.public`.

Three are published for other contexts:

- `AuditWriter` - append an audit row inside the caller's transaction (VS-010).
- `OutboxWriter` - queue a transactional email inside the caller's transaction.
- `IdempotencyStore` - claim an idempotency key inside the caller's transaction (VS-023).

The rest are Platform's own repository ports.
"""

from app.platform.application.ports.audit_writer import AuditWriter
from app.platform.application.ports.idempotency import IdempotencyStore
from app.platform.application.ports.outbox_writer import OutboxWriter
from app.platform.application.ports.repositories import AuditLog, IpHashSaltStore, SettingStore

__all__ = [
    "AuditLog",
    "AuditWriter",
    "IdempotencyStore",
    "IpHashSaltStore",
    "OutboxWriter",
    "SettingStore",
]
