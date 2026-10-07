"""Platform's ports: the interfaces its application layer and other contexts code against.

Pure `Protocol`s, one module per port - no SQLAlchemy, no infrastructure import - so the application
layer depends on these alone (CLAUDE.md, architecture rules; BUG-41). The
concrete adapters live in `app.platform.infrastructure`, and other contexts
obtain them only through `app.platform.public`.

Two are published for other contexts:

- `AuditWriter` - append an audit row inside the caller's transaction (VS-010).
- `OutboxWriter` - queue a transactional email inside the caller's transaction.

The rest are Platform's own repository ports.
"""

from app.platform.application.ports.audit_writer import AuditWriter
from app.platform.application.ports.outbox_writer import OutboxWriter
from app.platform.application.ports.repositories import AuditLog, SettingStore

__all__ = ["AuditLog", "AuditWriter", "OutboxWriter", "SettingStore"]
