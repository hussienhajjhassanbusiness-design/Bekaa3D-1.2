# VS-046 — Security data retention and IP-salt rotation: implementation plan

- **Status:** APPROVED by the owner with amendments A–G (see "Owner decisions" below); in implementation
- **Date:** 2026-10-16
- **Planned against:** `main` = `origin/main` = `a859066` (VS-026), alembic head `2e89860f5274`. **Re-pointed at implementation:** `main` = `c86a788` (VS-038 merged), `alembic heads` = **`58aac63240fc`** (wishlist_items), 17 revision files. VS-038 touched no settings files, so the seed count still moves 12 → 14.
- **Slice entry:** `docs/vertical-slice-plan.md:1153-1163`. Depends on VS-004 (Done).
- **SRS basis:** SEC-25 "Salted, rotating IP hashes" (`SRS.md:1501`), SEC-26 "PII redaction in structured logs" (`:1502`), SEC-07 (`:1483`), §21.4 (`:1318-1324`), §23 (`:1392-1406`), BR-122 (`:316`), BR-133 (`:327`). database-design.md §5.3 (`:542`), §5.4 (`:599-612`), §5.5 (`:616-627`), §19.11 (`:2199-2207`), §21.3 (`:2262-2269`), §23 matrix (`:2308-2318`).

---

## Owner decisions and amendments

All twelve recommendations in §12 are accepted, as written: Q1 7 d / 30 d, editable within 1–90 d; Q2 calendar month, with a daily cron plus `run_at_startup`; Q3 keep the `IP_HASH_SALT` name for the pepper; Q4 grace 0; Q5–Q7 are documented non-goals; Q8 no data exists, so no backfill; Q9 record the backup caveat in ADR-028; Q10 one audit row per rotation, counts only for the purge; Q11 spec edits approved, keeping edits to shared files minimal; Q12 the rotation period is a code rule.

Amendments, which take precedence over the text below:

- **A. Session retention clock.** The clock starts when the session **ends**, i.e. the **earlier** of `expires_at` and `revoked_at`. Predicate: `expires_at < c OR revoked_at < c`.
- **B. Missing key.** The refresh middleware also refreshes when no key is loaded. It is throttled by a separate last-attempt timestamp (at most once per `REFRESH_SECONDS`), so a missing salt row cannot hammer the database.
- **C. No module-level `asyncio.Lock`.** Single-flight uses an attempt-timestamp guard and must work across event loops (pytest-asyncio, one loop per `TestClient`).
- **D. Audit partition.** Verify whether `ensure_partitions` keeps `audit_logs` partitions ahead of the current month. If rotation can run before the partition exists, the failure must be safe (rotation rolls back; the next run retries), with a test.
- **E.** The step-3 checkpoint does not measure login p95.
- **F. Docs.** Also update the VS-002 wording and every doc saying an expired verification or reset link answers 410: after token retention it answers 400. ADR-028 states that a pepper change needs a restart (`get_settings` is `lru_cache`d).
- **G.** The `tests/unit` autouse fixture installs a test key and resets it to None after each test.

## 0. Verified findings (the six questions)

### Q1. Does any code compare an `ip_hash` across time or between rows?

**No.** It was checked in code across `src/` and `tests/`:

- `ip_hash` is only written in two places:
  - `sessions.ip_hash` (`identity/infrastructure/models.py:97`), written by `SessionRepository.add` (`repositories.py:435`);
  - `audit_logs.ip_hash` (`platform/infrastructure/models.py:85`), written by `SqlAuditWriter` (`audit_writer.py:59`).
- It is read back only by the mappers `_session_to_domain` (`identity/.../repositories.py:83`) and the audit mapper (`platform/.../repositories.py:95`). No `WHERE ip_hash = ...` exists, and no domain rule reads `Session.ip_hash`.
- The audit API deliberately omits it (`platform/api/schemas.py:90`).
- Reuse detection uses `token_version` and the token hash (`domain/entities.py:152-171`), never the IP.
- Throttling and rate limits do not use `hash_ip` at all; they key on the **raw** IP (see Q2 and §6).
- Tests only check `is not None`, the 64-hex width, or a value they wrote themselves (`test_deep_vs003_sessions.py:184`, `test_session_repository.py:47`, `test_deep_properties.py:310-312`).

**What breaks across a rotation:** nothing functional. The one property lost is the one SEC-25 wants lost: a hash written before the rotation can no longer be matched with one written after it, including by an operator in SQL. The `hash_ip` docstring's claim that the hash lets "audit/download logs ... detect repeat activity" (`core/security.py:38`) describes a use that no code has, and downloads were removed by ADR-019.

### Q2. Where are MFA login challenges stored, and do they hold IP hashes?

- **Where:** in Redis. The key is `mfa:challenge:{challenge_id}`, the value is `"{user_id}:{auth_epoch}"`, and the TTL is `CHALLENGE_TTL_SECONDS = 300` (`identity/application/services/mfa_session.py:34,61,80-103`). Redemption uses `GETDEL` (`:118`).
- **Completion flag:** `mfa:completed:{session_id}`, value `"1"`, with the TTL equal to the session lifetime (`:57,64-72`).
- **IP data:** neither key holds an IP or an IP hash. ADR-018 confirms the Redis storage.

Other Redis keys **do** hold the raw client IP:

| Key | Where | Lifetime |
|---|---|---|
| `ratelimit:{prefix}:{ip}` | `core/rate_limit.py:35,73` | Window TTL, 900–3600 s |
| `ratelimit:contact:ip:{ip}` | `engagement/api/contact_messages.py:98` | Window TTL |
| `login-throttle:{sha256(email)[:32]}:{ip}` and `...:inflight` | `identity/application/services/login_throttle.py:43-52` | `LOCKOUT_SECONDS = 900` and `INFLIGHT_TTL_SECONDS = 60` |

The email digest in the login-throttle key, and in `contact:email` (`contact_messages.py:107`), is an **unsalted** SHA-256 prefix. These are documented as limitations in §6, not fixed here.

### Q3. Does refresh-token reuse detection need revoked or expired session rows to still exist? Minimum safe retention?

**No.** The minimum safe retention for correctness is **zero**: a row may be deleted the moment it is revoked or expired. Evidence:

- `Session.authorize_rotation` checks `is_revoked`, then `is_expired`, and only then the version (`entities.py:160-165`). Reuse detection therefore fires only on a **live** session.
- On a revoked or expired row it raises `SessionRevokedError` / `SessionExpiredError`, both subclasses of `InvalidSessionError` (`domain/exceptions.py:58-75`).
- A missing row also raises `InvalidSessionError`: `get_owner_id` returns None (`refresh_session.py:59-61`), or `get_for_update` does (`:71-73`).
- The refresh route maps every `InvalidSessionError` to the same `unauthenticated_error()` (`identity/api/auth.py:375-376`). Deleted and revoked look identical to the client.
- Rotation does not extend `expires_at` (`repositories.py:444-446`). The refresh JWT's `exp` is the session's `expires_at` (`refresh_session.py:113-118`), and `_decode` requires and enforces `exp` (`session_tokens.py:97-106`). A refresh token for an expired session is refused before any row is read.
- Logout on a missing session is a no-op (`logout.py:19`).
- `current_claims` reads only `users.auth_epoch` and never the `sessions` row (ADR-018; `identity/api/dependencies.py:72`).
- No foreign key references `sessions`, `verification_tokens` or `password_reset_tokens`.

The only value of keeping ended rows is **forensic**: `reuse_detected_at`, `user_agent`, `ip_hash`. The security events those rows witness are already in the audit log (`session.reuse_detected` at `refresh_session.py:94-101`, `user.logged_in`, `user.logged_out`). Retention is therefore a privacy and forensics choice, not a correctness one.

The same holds for tokens, with one user-visible effect:
- An expired-but-present token answers `410 RESOURCE_EXPIRED`.
- An absent token answers `400 INVALID_TOKEN` (`auth.py:149-160, 489-500`). VS-002's Done-when says "A used token returns 400 and an expired one 410" (`vertical-slice-plan.md:96`).
- After the purge, an old link moves from 410 to 400. Token retention decides how long the friendlier 410 survives.
- Resend and reset cooldowns read the latest token's `created_at` and need 2 minutes (`verification.py:14,45`, `password_reset.py:24,63`). Any retention of 1 day or more is safe for them.

### Q4. How are admin-editable settings defined and seeded? What would new retention settings require?

The pattern comes from VS-007 and BR-133:
- **Rules** live in `platform/domain/settings_registry.py`: `SettingDefinition` entries in `_DEFINITIONS` (`:73`), exposed as `REGISTRY` and `ALL_KEYS` (`:218-224`). `unverified_account_purge_period` is the precedent (`:141-153`): DURATION, seconds, default `2_592_000`, minimum 7 days, maximum 90 days.
- **Values** are seeded **literally** by migration, not generated from the registry. Migration `de1d8a23512f` declares `_SEED` (`:55-68`) and inserts with `ON CONFLICT (key) DO NOTHING` (`:203-212`). Its comment says changing a default later is "a new migration (for fresh deployments) or a PATCH (for running ones)".
- **Reads:** consumers call `platform.public.settings_reader(session).get_duration_seconds(key)`. It validates on read and has **no fallback** (`purge_unverified.py:26-41`).
- **Docs:** `docs/settings-registry.md` holds the table and "The twelve settings".

Adding two settings requires:
1. Two `SettingDefinition` entries.
2. Seed rows in this slice's migration. The `type` column must be declared as the `setting_type` ENUM with `create_type=False`, as in `de1d8a23512f:20-40`; plain Text fails under asyncpg.
3. Downgrade deletes the two keys.
4. Update the count-pinned tests: `tests/integration/platform/test_settings_seed.py:32` asserts `len(rows) == 12`, and `tests/unit/platform/test_settings_registry.py:22,46` lists the required keys.
5. Update `settings-registry.md`.
6. Note the coordination point: VS-028 also edits the seed set (adds three keys, removes one; `vertical-slice-plan.md:674-676`), so whichever slice merges second rebases its counts.

### Q5. How do arq cron and `run_at_startup` behave for a monthly job when the worker was down on the scheduled day?

Verified against arq **0.28.0**, the pinned version (`requirements.txt:69`), in `arq/worker.py` `run_cron` and `arq/cron.py` `cron()`:

- **Missed ticks are skipped.** At startup, a job's `next_run` is computed forward from "now" with `calculate_next(n)`. A run missed while the worker was down never happens; there is no catch-up.
- **`run_at_startup=True`** sets `next_run = n`, the worker start time, so the job runs once at every worker start.
- **`unique=True`** (the default) makes `job_id = f"{name}:{to_unix_ms(next_run)}"`:
  - For a scheduled tick, every worker computes the same id, so only one enqueue wins.
  - For a startup run, the id contains each worker's **own start time**, so two workers starting at different milliseconds both run it.
  - Cron defaults are `keep_result=0` and `max_tries=1`, so arq's dedupe is weak.
- **Consequence:** `cron(day=1, ...)` alone loses the month whenever the worker is down at 00:xx on the 1st. Idempotency and mutual exclusion must come from PostgreSQL. `ensure_partitions` already does this with an advisory lock (`partitions.py:37,87`).

### Q6. How does `purge_unverified_accounts` handle batching, retention reads and idempotency?

`jobs/purge_unverified.py:36-49` and `UserRepository.purge_never_verified_before` (`identity/infrastructure/repositories.py:334-366`):

- **Batching:** none. One transaction, one `DELETE ... RETURNING id`.
- **Retention read:** in the same transaction as the delete, through `settings_reader(...).get_duration_seconds(...)`, with **no fallback**. An invalid setting raises and the job fails visibly.
- **Idempotency:** the predicate is "older than cutoff and never verified", so a second run deletes nothing.
- **Logging:** a structured line only when something was deleted (`unverified_accounts_purged`, count and retention). No audit row.
- **Deviation:** the job calls a **repository**, not a use case, which departs from ADR-011 ("Job entrypoints call application use cases rather than embedding business logic/raw SQL"). VS-046 must not copy that part.

Reused here: the settings read with no fallback, the predicate-based idempotency, and the count log. Changed here: a use case between job and repository, and batches (§2.3).

---

## 1. Scope and non-goals

### In scope
1. **`ip_hash_salts` table.** Platform context. Holds exactly one current random salt (32 bytes), enforced by the database. It is seeded with one salt by the migration.
2. **`hash_ip` becomes keyed.** It computes `HMAC-SHA256(K, ip)`, where `K` is derived from the env pepper `IP_HASH_SALT` and the current database salt. It stays **synchronous**, served from an in-process cache that refreshes from PostgreSQL.
3. **`rotate_ip_salt` job.** Rotates at most once per UTC calendar month, catches up after downtime, is safe on two workers, and deletes the old salt in the same transaction. It writes one audit row containing ids only.
4. **`purge_expired_security_records` job**, daily. It deletes `verification_tokens` and `password_reset_tokens` past `expires_at + security_token_retention_period`, and `sessions` whose end, the **earlier** of `expires_at` and `revoked_at`, is older than `session_retention_period` (amendment A). It is batched, uses `SKIP LOCKED`, and never touches live rows.
5. **Two settings**, admin-editable (BR-133), seeded by the migration.
6. **Secret hygiene:**
   - `ip_hash_salt` becomes `SecretStr`;
   - the logging redaction keys gain `ip_hash_salt`, `salt` and `pepper`;
   - salt bytes are generated inside PostgreSQL, so they never appear as a bound parameter;
   - the salt is excluded from every repr, log, error and audit row.
7. **Docs:** a new ADR-028, SRS §23 and §34 lists, the plan entry, settings-registry.md, CONTRIBUTING "Secrets", `.env.example` comment, README status. Also the stale references: the `hash_ip` docstring, `platform/api/schemas.py:90` and `openapi.json:1220` (CLAUDE.md), and `tests/unit/test_deep_architecture.py:1` (CLAUDE.md).

### Non-goals (documented, not fixed)
- Raw client IPs and unsalted email digests in Redis keys (§6, owner question 5).
- Audit-log 24-month hot retention and archiving (SRS §21.4; owner question 6).
- `mfa_recovery_codes` retention (owner question 7).
- Re-hashing or nulling legacy `ip_hash` values. There is no production deployment yet (VS-020 is "Not started"), so legacy hashes exist only in development databases (owner question 8).
- Backup retention of old salts (VS-047; owner question 9).
- Admin "run job now" endpoints. Explicitly excluded by api-endpoints.md §34 (`:1508`).

---

## 2. Jobs and settings

### 2.1 Settings (registry and seed)

| Key | Type | Default | Min | Max | Public | Meaning |
|---|---|---|---|---|---|---|
| `security_token_retention_period` | duration (s) | `604_800` (7 d) | `86_400` (1 d) | `7_776_000` (90 d) | no | Age **past `expires_at`** at which a verification or password-reset token row is deleted. |
| `session_retention_period` | duration (s) | `2_592_000` (30 d) | `86_400` (1 d) | `7_776_000` (90 d) | no | Age **past the end** of a session (expiry or revocation, whichever came first) at which the row is deleted. |

Why these values:
- **Tokens, 7 days:** keeps the `410` "link expired" answer for a week after expiry, which covers a user opening an old email (Q3). The row holds only a hash, so privacy cost is low.
- **Sessions, 30 days:** the rows hold `ip_hash` and `user_agent`, which are personal data. 30 days covers a month of support or forensic questions, and the audit log keeps the events. Both values are owner question 1.
- **Minimum 1 day, not 0:** Q3 shows 0 is safe, but 1 day keeps an operator's same-day look at a reuse incident possible.

### 2.2 `rotate_ip_salt`

- **Registry:** `cron(rotate_ip_salt, hour=0, minute=23, second=0, run_at_startup=True)`. It is **daily**, off the hour, not on 00:07 (`ensure_partitions`) or 03:17/03:41.
- **Rule:** rotate when the current salt's `created_at < date_trunc('month', now() AT TIME ZONE 'UTC')`, or when no current salt exists (self-heal).
- **Effect:** rotation happens at most once per UTC calendar month and at the first run of a new month. After downtime, the startup run or the next daily tick catches up. A second run in the same month is a no-op (Q5).
- **Why not `day=1`:** arq skips missed ticks (Q5). A daily check costs one indexed single-row read.
- **Why not "older than 30 days":** an age rule drifts later after every catch-up, while the month rule is anchored. Owner question 2.
- **Concurrency:** a transaction-scoped advisory lock (`IP_HASH_ROTATION_LOCK_KEY`, a fixed constant like `ENSURE_PARTITIONS_LOCK_KEY`), then the age re-check under the lock. The partial unique index is the backstop.
- **Monitoring:**
  - `ip_hash_salt_rotated` (new salt id; ids and timestamps only) or `ip_hash_salt_rotation_not_due` at debug level.
  - A database error is **raised** (unlike `ensure_partitions`, which swallows), so arq marks the job failed and the VS-047 heartbeat alert sees it.
  - An audit row: `action="ip_hash_salt.rotated"`, `entity_type="IpHashSalt"`, `entity_id=<new id>`, `actor_user_id=None`, `before_data={"previous_salt_id": "<uuid>"}`. No salt bytes.

### 2.3 `purge_expired_security_records`

- **Registry:** `cron(purge_expired_security_records, hour=3, minute=29, second=0)`. No `run_at_startup`: missing a day is harmless, and the next run deletes the backlog.
- **Settings read:** both settings are read once, in their own short transaction at job start, with no fallback. Cutoffs: `token_cutoff = now - security_token_retention_period`, `session_cutoff = now - session_retention_period`. If either setting is invalid, the job raises before deleting anything.
- **Batches:** each batch is its own short transaction. The job calls the use case `PurgeExpiredSecurityRecords.execute_batch(...)`, which deletes up to `BATCH_SIZE = 1000` rows per table. The job loops until each table returns fewer than `BATCH_SIZE`, or until `MAX_BATCHES_PER_RUN = 50` per table. At the cap it logs `truncated=true` and resumes the next day. This bounds runtime well under arq's default `job_timeout`; `WorkerSettings` sets none (`worker.py:50-59`). arq's 300 s default was not re-read in source.
- **Fixed `now`:** `now` is computed once per run. The job takes `now: datetime | None = None` like `ensure_partitions`, so tests can pin it (§5.6).
- **Logging:** `security_records_purged` with `verification_tokens`, `password_reset_tokens`, `sessions`, `truncated` and both retention values, and only when something was deleted (as `purge_unverified.py:44-49`). No audit row per deleted row, same as the precedent (owner question 10).

---

## 3. Layers, function by function

Conventions followed (from VS-026 and VS-033):
- Application commands live under `<context>/application/commands/`.
- Ports live in `<context>/application/ports(.py)`.
- SQLAlchemy lives only in `infrastructure/`.
- Cross-context access goes only through `platform.public` (`tests/unit/test_deep_architecture.py:96-118`).
- `app.core`, `app.jobs`, `app.api` and `app.worker` are composition roots, exempt from the layer rules (`test_deep_architecture.py:8-9`).

### 3.1 Domain

**`platform/domain/entities.py`:** add `IpHashSalt`. The salt is excluded from `repr` and `eq`.
```python
@dataclass(frozen=True)
class IpHashSalt:
    id: UUID
    created_at: datetime
    salt: bytes = field(repr=False, compare=False)  # never printed, never compared
```

**`platform/domain/ip_hash_rotation.py`:** a pure rule for testing.
```python
def rotation_due(current_created_at: datetime | None, now: datetime) -> bool:
    """Due when there is no salt or it predates the current UTC month (SEC-25)."""
    if current_created_at is None:
        return True
    month_start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return current_created_at < month_start
```

**Identity domain:** no change. `Session.is_live` and the token entities already define "live".

### 3.2 Application

**Platform ports** (`platform/application/ports/repositories.py`):
```python
class IpHashSaltStore(Protocol):
    async def lock_rotation(self) -> None: ...                 # pg_advisory_xact_lock
    async def current_created_at(self) -> tuple[UUID, datetime] | None: ...  # no salt bytes
    async def replace_current(self) -> UUID: ...               # delete all, insert server-generated
    async def load_current(self) -> IpHashSalt | None: ...
```

**`platform/application/commands/rotate_ip_hash_salt.py`:**
```python
class RotateIpHashSalt:
    async def execute(self, *, now: datetime) -> UUID | None:
        """Returns the new salt id, or None when not due. Caller owns the transaction."""
        await self._salts.lock_rotation()
        current = await self._salts.current_created_at()
        if not rotation_due(current[1] if current else None, now):
            return None
        new_id = await self._salts.replace_current()
        await self._audit.record(actor_user_id=None, action="ip_hash_salt.rotated",
                                 entity_type="IpHashSalt", entity_id=new_id,
                                 before_data={"previous_salt_id": str(current[0]) if current else None},
                                 request_id=None, ip_hash=None)
        return new_id
```
Verified: `AuditWriter.record` takes `actor_user_id: UUID | None`, `before_data` and `after_data` as optional dicts, and `request_id` and `ip_hash` defaulting to None (`platform/application/ports/audit_writer.py:14-25`).

**Identity ports** (`identity/application/ports.py`): add one method each.
- `VerificationTokenStore.delete_expired_batch(*, cutoff: datetime, limit: int) -> int`
- `PasswordResetTokenStore.delete_expired_batch(*, cutoff: datetime, limit: int) -> int`
- `SessionStore.delete_ended_batch(*, cutoff: datetime, limit: int) -> int`

**`identity/application/commands/purge_expired_security_records.py`:**
```python
@dataclass(frozen=True)
class PurgeBatchResult:
    verification_tokens: int
    password_reset_tokens: int
    sessions: int

class PurgeExpiredSecurityRecords:
    async def execute_batch(self, *, token_cutoff: datetime, session_cutoff: datetime,
                            limit: int) -> PurgeBatchResult:
        """One batch per table; the caller loops and owns each transaction."""
        if token_cutoff >= self._now() or session_cutoff >= self._now():
            raise ValueError("cutoff must be in the past")  # guards live rows (SEC-07)
        ...
```
The cutoff guard is defence in depth. The settings minimum is already 1 day.

### 3.3 Infrastructure

**`platform/infrastructure/models.py`:** add `IpHashSaltModel` (`__tablename__ = "ip_hash_salts"`) and its `__table_args__` (§4).

**`platform/infrastructure/repositories.py`:** add `SqlIpHashSaltStore`.
- **`lock_rotation`:** `SELECT pg_advisory_xact_lock(:key)`, with `IP_HASH_ROTATION_LOCK_KEY = 0x62656B6149505348  # "bekaIPSH"`.
- **`current_created_at`:** `SELECT id, created_at FROM ip_hash_salts WHERE is_current`. It does **not** select `salt`.
- **`replace_current`:** `DELETE FROM ip_hash_salts;` then `INSERT INTO ip_hash_salts (salt, is_current) VALUES (gen_random_bytes(32), true) RETURNING id`. The bytes are generated by `pgcrypto`, which is installed by baseline `24d82aa2fbee:19`, so they never travel as a bound parameter. A driver error can then never echo them.
- **`load_current`:** `SELECT id, created_at, salt FROM ip_hash_salts WHERE is_current`. This is the only reader of the bytes.

**Identity repositories** (`identity/infrastructure/repositories.py`): add the three batch deletes. Query shape:
```sql
DELETE FROM verification_tokens WHERE id IN (
  SELECT id FROM verification_tokens WHERE expires_at < :cutoff
  LIMIT :limit FOR UPDATE SKIP LOCKED)
```
- `password_reset_tokens` uses the same shape.
- `sessions` uses `WHERE expires_at < :cutoff OR revoked_at < :cutoff`. `revoked_at < :cutoff` is false for NULL, so live rows (`revoked_at IS NULL AND expires_at > now`) can never match, because `cutoff < now`.
- All return `rowcount`.

### 3.4 `core`: keyed `hash_ip` with an in-process key

**`core/config.py`:** `ip_hash_salt: SecretStr`. Its meaning is now the **pepper**; the env name is kept (owner question 3). `get_secret_value()` is called in exactly one place.

**`core/security.py`:**
```python
@dataclass(frozen=True)
class _IpHashKey:
    salt_id: UUID
    loaded_at: float                       # time.monotonic()
    material: bytes = field(repr=False)    # derived key; never printed

_current_key: _IpHashKey | None = None

def install_ip_hash_key(*, salt_id: UUID, salt: bytes, now: float) -> None:
    """Derive K = HMAC(pepper, label || salt); either secret alone reveals nothing."""
    pepper = get_settings().ip_hash_salt.get_secret_value().encode("utf-8")
    material = hmac.new(pepper, b"bekaa3d/ip-hash/v2:" + salt, hashlib.sha256).digest()
    global _current_key
    _current_key = _IpHashKey(salt_id=salt_id, loaded_at=now, material=material)

def hash_ip(ip_address: str) -> str | None:
    """Keyed hash for audit and session rows; None until a key is loaded (SEC-25)."""
    key = _current_key
    if key is None:
        return None
    return hmac.new(key.material, ip_address.encode("utf-8"), hashlib.sha256).hexdigest()
```
- **Output:** still 64 lowercase hex characters, so log redaction (`logging.py:62`) and the existing width tests still hold.
- **Return type:** becomes `str | None`. All 16 call sites already feed `str | None` fields (`... if ip else None`), so their types are unchanged. mypy confirms this at step 3.

**New `core/ip_hash_keyring.py`** (composition root; reads through `platform.public`):
```python
REFRESH_SECONDS = 60

async def refresh_ip_hash_key(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Reload the current salt; on failure keep the old key and log the error class only."""
```
- Single-flight comes from an attempt-timestamp guard, not an `asyncio.Lock` (amendment C): a caller claims the next attempt slot under a `threading.Lock` held for no `await`, so the guard works across event loops. Concurrent requests keep using the current key and do not wait.
- The guard also throttles the no-key case (amendment B): with no key loaded, the middleware retries at most once per `REFRESH_SECONDS`.
- Logs: `ip_hash_key_refresh_failed` with `error=type(exc).__name__`, the same pattern as `partitions.py:96-100`. When no salt row exists it logs `ip_hash_key_missing`, warning level, at most once per interval.

**Wiring (API):**
- **Lifespan** (`main.py:23-38`): after the session factory is created, call `await refresh_ip_hash_key(...)` once. This is **best-effort**: a DB outage at boot does not stop the API, and requests that need the DB fail on their own.
- **Middleware:** add `IpHashKeyRefreshMiddleware` in `app/api/middleware.py`. On a request, if no key is loaded or `time.monotonic() - key.loaded_at > REFRESH_SECONDS`, and the attempt guard grants the slot, it awaits the refresh before the handler runs.
- **Test app:** register the middleware in `tests/conftest.py:make_app` too, since that fixture mirrors `main.py` (`conftest.py:124-125`).

**Wiring (worker):** none. The worker does not hash IPs. The rotation job writes the salt and does not need the key.

### 3.5 Jobs (thin; call use cases only)

**`jobs/rotate_ip_salt.py`:**
```python
async def rotate_ip_salt(ctx: dict[str, Any], *, now: datetime | None = None) -> bool:
    """arq job: rotates at most once per UTC month; safe on any number of workers."""
    async with ctx["session_factory"]() as session, session.begin():
        new_id = await RotateIpHashSalt(platform_public.ip_hash_salt_store(session),
                                        platform_public.SqlAuditWriter(session)
                                        ).execute(now=now or datetime.now(UTC))
    ...  # log ids only
```
Add `ip_hash_salt_store(session)` and `current_ip_hash_salt(session)` to `platform/public.py`.

**`jobs/purge_security_records.py`:** `purge_expired_security_records(ctx, *, now=None) -> dict[str, int]`, with the loop from §2.3. Each batch is `async with session_factory() as s, s.begin(): await PurgeExpiredSecurityRecords(...).execute_batch(...)`.

**`jobs/registry.py`:** add both to `FUNCTIONS` and `CRON_JOBS` with one comment line each, as the existing ones have.

### 3.6 Logging and secret hygiene

- **`core/logging.py:15-35`:** add `"ip_hash_salt"`, `"salt"`, `"pepper"`, `"ip_hash_key"` to `_SENSITIVE_KEYS`.
- **No new regex.** The salt never exists as a hex string in Python: it is `bytes` from the DB, and the pepper is a `SecretStr`.
- **The salt never appears:**
  - in a bound parameter (generated server-side);
  - in a `repr` (`field(repr=False)`, `SecretStr`);
  - in an error (the error class is logged only);
  - in an audit row (ids only);
  - in the API (no endpoint).

---

## 4. Database

**One migration**, e.g. `xxxxxxxxxxxx_ip_hash_salts_and_retention_settings.py`, with `down_revision = "58aac63240fc"` (the head at implementation time; originally planned against `2e89860f5274`), or the head at rebase time.

### 4.1 Upgrade
1. Create `ip_hash_salts`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `salt BYTEA NOT NULL`
   - `is_current BOOLEAN NOT NULL DEFAULT true`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()`. Use `clock_timestamp`, not `now()`, as migration `5e1c0a7d2b94` did for audit_logs, so two rows in one transaction get distinct times.
   - `CHECK (octet_length(salt) = 32)` named `ck_ip_hash_salts_salt_length`.
2. Add the partial unique index `uq_ip_hash_salts_one_current ON ip_hash_salts (is_current) WHERE is_current`. This lets the **database** enforce "at most one current". "At least one" is guaranteed by the seed and by rotation's delete-then-insert happening in one transaction. The application tolerates zero: `hash_ip` returns None, and the next rotation run self-heals.
3. Seed: `INSERT INTO ip_hash_salts (salt) VALUES (gen_random_bytes(32))`.
4. Seed the two settings literally with `ON CONFLICT (key) DO NOTHING`, following `de1d8a23512f:55-68,203-212`, with the `setting_type` ENUM column declared `create_type=False`.
5. **No index changes** (§4.3).

### 4.2 Downgrade
- `DELETE FROM settings WHERE key IN ('security_token_retention_period', 'session_retention_period')`.
- Drop the index, then the table.
- Check that this is reversible: `alembic downgrade -1 && alembic upgrade head` (CONTRIBUTING). `tests/integration/test_migration_reversibility.py` already exercises the chain.

### 4.3 Indexes: none added in this slice (justified by query shape)

| Purge statement | Usable index? | Expected size at steady state |
|---|---|---|
| `verification_tokens WHERE expires_at < c` | **No.** `ix_verification_tokens_expires_at_live` is partial on `used_at IS NULL`, and the planner can use it only when the query implies that predicate. A seq scan follows. | Rows created over the last 24 h + 7 d (tokens per registration and resend). |
| `password_reset_tokens WHERE expires_at < c` | **No**, same reason. | 1 h + 7 d of reset requests. |
| `sessions WHERE expires_at < c OR revoked_at < c` | Partly. `ix_sessions_expires_at_live` (`WHERE revoked_at IS NULL`) could serve only the `revoked_at IS NULL AND expires_at < c` half; the OR as a whole is a seq scan. | Logins over 30 d (lifetime) + 30 d (retention). |

**Decision:** no new index. All three tables are bounded by the purge itself to roughly days or weeks of rows. A daily job running `LIMIT 1000 ... SKIP LOCKED` batches over a table of that size is cheap, and an index would add write cost to the login path on every insert.

**Do not drop or replace** the existing partial indexes. They are pinned by name in `tests/integration/test_migration_reversibility.py:89` and `tests/integration/test_outbox_payload_backfill.py:232`. They encode database-design.md §19.11.

**To verify later with `EXPLAIN (ANALYZE, BUFFERS)`** on staging-sized data (VS-020 or VS-048), not in CI:
- (a) Batch time for `sessions` at 1M rows with 10% purgeable. If a batch takes more than 200 ms, add `CREATE INDEX CONCURRENTLY ix_sessions_ended ON sessions (revoked_at) WHERE revoked_at IS NOT NULL`, and split the delete into two statements: an `expires_at` branch through the live partial index and a `revoked_at` branch.
- (b) The same check for the token tables at 1M rows.
- (c) That `FOR UPDATE SKIP LOCKED` with `LIMIT` does not re-scan already-skipped heap pages excessively.

EXPLAIN-based assertions in tests are planner- and statistics-dependent, and therefore flaky. Record the measurements in the PR instead, as VS-016 did for search latency.

### 4.4 Compatibility, lock and rebase
- **Backward compatible:**
  - Old code ignores the new table.
  - Old code lists the two extra settings rows in the admin list without validation (`platform/infrastructure/repositories.py:250-275` reads rows directly), which is harmless.
  - New code on an old schema is impossible, because `alembic upgrade head` runs before new code serves traffic (`de1d8a23512f:196-201`).
- **Exactly one head:** this slice adds a migration, so **the migration lock applies** (`CONTRIBUTING.md:20-74`):
  - Announce the lock and generate early.
  - Merge the migration in its own small PR if the slice runs long.
  - **Rebase onto `main` before the PR**, and re-point `down_revision` by regenerating, never by hand-editing, if VS-028 or another migration landed first.
  - Check `alembic heads` shows exactly one revision and `alembic upgrade head` passes.

---

## 5. Performance and abuse

### 5.1 Request paths
- **Before:** `hash_ip` did one SHA-256.
- **After:** one HMAC-SHA256 on a pre-derived key, plus a monotonic-clock comparison in the middleware. The key derivation, a second HMAC, runs only on refresh.
- **Refresh cost:** at most one indexed single-row `SELECT` per process per 60 s, and only while traffic flows. No Redis is involved, consistent with ADR-018's stance on Redis as authority.

### 5.2 Rotation staleness across processes
- After a rotation commits, each API process keeps hashing with the old derived key for at most `REFRESH_SECONDS` (60 s), plus its next request.
- Hashes written in that window are linkable to pre-rotation hashes. This is acceptable: about one minute per month, and no code compares hashes (Q1).
- The old **salt** is gone from PostgreSQL at commit, so the **grace window in the database is 0** (owner question 4). The old derived key lives only in process memory, until the next refresh or a restart.

### 5.3 Failure modes

| Failure | Behaviour |
|---|---|
| DB read fails during refresh | The previous key stays in use; error class logged. No request fails because of it. |
| No key ever loaded (fresh process, DB down at boot) | `hash_ip` returns None, and rows store `ip_hash = NULL` (the column is nullable). This fails closed for privacy and open for availability. |
| Rotation transaction fails | The old salt stays current; the job raises; the next daily or startup run retries. |
| Purge setting invalid | The job raises before any delete (no fallback, BR-133). |

### 5.4 Locking and deadlocks
The purge **never waits and never takes `users` locks**:
- `SKIP LOCKED` skips any token or session row held by `VerifyEmail`, `ConfirmPasswordReset` (`lock_all_for_user`, `repositories.py:696`), `RefreshSession` (`get_for_update`, `:385`), `Logout`, or `revoke_all_for_user` (`:458-475`).
- `revoke_all_for_user` updates **expired-but-not-revoked** rows (`WHERE revoked_at IS NULL`, `:473`), which are exactly the rows the purge also targets. Without `SKIP LOCKED`, a multi-row purge DELETE could deadlock against a reset holding `users` and then `sessions`.
- With `SKIP LOCKED`, the purge cannot be part of a wait cycle, so ADR-018's lock order (`users` before `sessions`) is preserved.

### 5.5 Concurrent runs
- **Two purges:** they take disjoint rows through `SKIP LOCKED`, the sum of counts equals the purgeable rows, and a rerun deletes 0.
- **Two rotations:** they serialise on the advisory lock, and the second sees a salt created this month and returns None. The partial unique index rejects any second current row from a path that bypassed the lock.

### 5.6 Abuse
No new endpoint. Rotation cannot be triggered from outside, since jobs are not exposed (api-endpoints.md §34).

---

## 6. Known limitations (documented, not fixed)

| # | Limitation | Evidence | Proposal |
|---|---|---|---|
| L1 | Raw client IP in Redis rate-limit and login-throttle keys | `rate_limit.py:35,73`; `contact_messages.py:98`; `login_throttle.py:48` (TTL ≤ 1 h; lockout 15 min) | Non-goal. Follow-up with VS-020, which changes forwarded-IP handling anyway: key on `hash_ip(ip)`. Owner question 5. |
| L2 | Unsalted `sha256(email)[:32]` in Redis keys is reversible by dictionary | `login_throttle.py:47`; `contact_messages.py:107` | Same follow-up as L1: HMAC with the same key. |
| L3 | Audit log: SRS §21.4 "24 months hot, then archived"; nothing drops or archives partitions; `audit_logs.ip_hash` stays as written | `SRS.md:1322`; `partitions.py` only creates | Non-goal. Owner question 6: assign to VS-047 or a new slice. After VS-046, hashes older than one month are already unlinkable, which reduces the urgency. |
| L4 | `mfa_recovery_codes` used rows never purged ("retention purge allowed", `database-design.md:2318`) | Unused codes are deleted on regeneration (`mfa_regenerate_recovery_codes.py:65`) | Non-goal; at most 10 rows per regeneration and no IP data. Owner question 7. |
| L5 | Database backups contain old salts, so unlinkability holds only after backup retention expires | VS-047 (`vertical-slice-plan.md:1165-1185`) | Record in ADR-028. Owner question 9. |
| L6 | Hashes written up to 60 s after a rotation use the old key | §5.2 | Accept and document. |

---

## 7. Tests (per category, with edge cases)

**Isolation rule.** The shared database has no per-test rollback (`tests/conftest.py:152-159`). Therefore:
- every purge test creates its own user and rows **far in the past** (`expires_at` in the year 2000);
- it calls the job with `now=datetime(2000, 3, 1, tzinfo=UTC)`, so the cutoff lies in 2000 and **only rows from that era** can match;
- it asserts presence or absence **by row id**, and `>=` on returned counts, never equality on global counts.

Rotation is global state (one current salt). Rotation tests pass `now` relative to the current salt's `created_at` and never assume a specific salt id. Other tests only assert `ip_hash is not None` or width, so they survive a rotation.

### 7.1 Unit (`tests/unit/...`)
- **`core/test_ip_hash.py`:**
  - deterministic for the same key;
  - 64 lowercase hex characters;
  - the raw IP is not a substring;
  - different salt gives a different hash, and different pepper gives a different hash;
  - returns None when no key is installed;
  - `repr(_current_key)` and `repr(get_settings())` do not contain the salt or the pepper;
  - IPv6 and IPv4-mapped inputs;
  - an empty string is never passed (callers guard with `if ip`). Assert that with a property test, or document it.
- **`tests/unit/conftest.py`:** add an autouse fixture calling `install_ip_hash_key(salt_id=UUID(int=1), salt=b"\x01" * 32, now=0.0)`, and reset the key to None (and the attempt guard) after each test (amendment G). Then `test_deep_properties.py:310-312` keeps passing with env-only settings. `IP_HASH_SALT` stays in the placeholder env (`:25`), along with `test_error_contract.py:23` and `test_health.py:14`.
- **`platform/test_ip_hash_rotation_rule.py`:**
  - None means due;
  - the last microsecond of the previous month means due;
  - the first instant of this month means not due;
  - a non-UTC `now` is normalised;
  - a current salt dated in the future (clock skew) means not due.
- **`identity/test_purge_cutoff_guard.py`:** a cutoff ≥ now raises.
- **`platform/test_settings_registry.py`:** the two keys are present, typed DURATION, not public, defaults within range. Update `REQUIRED_KEYS` and the count (`:22,46`).
- **`test_logging_redaction`:** `{"ip_hash_salt": "...", "salt": b"..."}` is redacted.

### 7.2 Integration (`tests/integration/...`, PostgreSQL and Redis)
- **`platform/test_ip_hash_salts_schema.py`:**
  - the migration seeded exactly one current row;
  - a second `is_current = true` insert raises `UniqueViolation`;
  - a 31-byte salt violates the CHECK;
  - the `salt` column is never selected by `current_created_at` (assert on the compiled SQL, or with a spy session).
- **`platform/test_rotate_ip_salt.py`:**
  - not due means no-op (same id, no audit row);
  - due means a new id, the old row is gone, the table count is 1, and exactly one `ip_hash_salt.rotated` audit row exists with `before_data.previous_salt_id` and no bytes anywhere in `before_data`/`after_data`;
  - a second run with the same `now` is a no-op;
  - an empty table self-heals.
- **`identity/test_ip_hash_after_rotation.py`** (the "Done when"):
  1. Log in and read the stored `sessions.ip_hash`.
  2. Rotate with a forced `now`.
  3. Refresh the keyring through the app (or wait out `REFRESH_SECONDS` with an injectable clock).
  4. Log in again from the same IP, and see a **different** hash.
  5. Check that the audit rows and the session row are written and refresh still works.
- **`identity/test_purge_expired_security_records.py`:**
  - **verification tokens:** live (`expires_at > now`) survives; expired within retention survives; past retention is deleted; used and past retention is deleted;
  - **reset tokens:** the same cases;
  - **sessions:** live survives; revoked within retention survives; revoked past retention is deleted; expired past retention is deleted; expired within retention but revoked long ago is deleted (the OR); `revoked_at IS NULL AND expires_at < cutoff` is deleted;
  - a rerun deletes 0;
  - `truncated` appears when more than `BATCH_SIZE * MAX_BATCHES_PER_RUN` rows exist (use a test-only small batch size argument);
  - an invalid retention setting raises and nothing is deleted.
- **`identity/test_purge_user_facing.py`:**
  - an expired verification link answers `410` before the purge and `400 INVALID_TOKEN` after it;
  - a revoked session's refresh token answers the same 401 body before and after the purge;
  - the resend cooldown is unaffected.
- **`platform/test_settings_seed.py`:** update `len(rows) == 12` to 14. The "seeded values are the registry defaults" test covers the new keys automatically.
- **`test_migration_reversibility.py`:** the new revision downgrades cleanly; the settings keys and the table are gone after `downgrade -1`.
- **`test_worker_registry`** (new or extended): both jobs are in `FUNCTIONS` and `CRON_JOBS`; `rotate_ip_salt` has `run_at_startup=True`; purge has a daily schedule.

### 7.3 Concurrency (`tests/concurrency/...`)
- **`test_ip_salt_rotation_race.py`:** two `rotate_ip_salt` runs at once with a due `now`. Exactly one returns True, one audit row exists, and the table count is 1.
- **`test_purge_vs_password_reset.py`:** a reset confirm holds `users` and then `sessions` (it updates expired-not-revoked rows) while the purge runs. There is no deadlock and no wait over the timeout, the purge skips the locked rows, and a later purge deletes them.
- **`test_purge_vs_refresh.py`:** a refresh holding `get_for_update` on a live session while the purge runs. The live session survives and the refresh succeeds.
- **`test_concurrent_purges.py`:** two purges over 3 × `BATCH_SIZE` purgeable rows. The sum of counts equals the rows created, and there are no errors.

### 7.4 Security
- **`tests/security/test_ip_salt_never_leaks.py`:**
  - run a rotation and a purge with log capture;
  - assert no captured log line, audit row or exception string contains the salt bytes (hex or base64) or the pepper;
  - force a DB error during rotation (e.g. a closed connection) and assert only the error class is logged.

### 7.5 Smoke
- Add `tests/smoke/test_vs046_smoke.py` listing the "Done when" node ids, following `tests/smoke/test_vs033_smoke.py`.
- Register it in `tests/conftest.py:20-45`.

---

## 8. Docs and ADRs

- **New ADR-028**, "Keyed, monthly-rotated IP hashes: database salt plus environment pepper, old salts deleted". It needs a new ADR because the change is expensive to reverse: it changes hash format and secret semantics and deliberately drops salt history. Content:
  - the Q1 finding;
  - the options in §10.1 to §10.3;
  - the 60 s staleness;
  - the backup caveat L5;
  - "PHONE_HASH_SALT is unaffected" (ADR-024);
  - a pepper change needs a process restart, because `get_settings` is `lru_cache`d (amendment F).
  - Add it to `docs/adr/README.md`.
- **410 → 400 after retention** (amendment F): the VS-002 Done-when and every doc that says an expired verification or reset link answers 410 note that, once the token is purged, the link answers `400 INVALID_TOKEN`.
- **SRS** (owner approval, question 11):
  - §23 (`SRS.md:1394-1406`): add `purge_expired_security_records | Daily | Deletes expired verification and reset tokens and ended sessions past their retention.`
  - Reword `rotate_ip_salt` cadence to "Daily check; rotates once per calendar month".
  - §24 secrets (`:1425`): "IP hash salt" becomes "IP hash pepper (env); rotating salts live in the database".
- **api-endpoints.md §34** (`:1508-1525`): add `purge_expired_security_records`.
- **database-design.md:**
  - add an `ip_hash_salts` section;
  - in §21.3, state the two retention settings;
  - in the §23 matrix, sessions and both token tables become "retention purge (`purge_expired_security_records`)".
- **`docs/settings-registry.md`:** two rows; "twelve" becomes "fourteen"; the rationale from §2.1.
- **`docs/vertical-slice-plan.md`:**
  - VS-046 entry: correct "versioned salts" to "one current salt, old ones deleted", "replacing IP_HASH_SALT" to "pepper kept", and "monthly" to "daily check, monthly rotation";
  - Status → Done at merge;
  - the plan table row.
- **CONTRIBUTING.md "Secrets"** (`:113-121`): `IP_HASH_SALT` is now the pepper. The brute-force sentence becomes "needs both the pepper and a salt that is deleted monthly".
- **`.env.example:27`:** a comment-only change; the name is kept.
- **README.md Status:** add the VS-046 line.
- **Stale references:**
  - `core/security.py:38-40`: the docstring drops "download logs" and points at ADR-028.
  - `platform/api/schemas.py:90`: replace "(CLAUDE.md, local secrets)" with "(CONTRIBUTING.md "Secrets", ADR-028)".
  - Regenerate `docs/frontend-handoff/openapi.json` with `scripts/export_openapi.py`, so `:1220` follows.
  - `tests/unit/test_deep_architecture.py:1`: "The CLAUDE.md architecture rules" becomes "The ADR-005 architecture rules".
- **New `docs/security-retention.md`:** a short operator page covering what is purged when, how to change the settings, the rotation rule, and the limitations L1 to L6. This follows `docs/address-book.md`.

---

## 9. Implementation steps

Steps are small, and each one ends green.

1. **Branch** `vs-046-security-retention` from fresh `main`. **Announce the migration lock.**
2. **Migration only** (separate PR if the lock must be released fast):
   - the table, partial unique index, CHECK, seed salt, seed settings, downgrade;
   - registry entries and the count-pinned settings tests;
   - schema tests from §7.2;
   - `alembic heads` shows one head; `upgrade head`, `downgrade -1`, `upgrade head` all pass.
3. **Keyed `hash_ip`** (risky middle step):
   - `SecretStr`, `_IpHashKey`, `install_ip_hash_key`, new `hash_ip`;
   - the keyring refresher, the lifespan load, the middleware in both `main.py` and `tests/conftest.py:make_app`;
   - the unit autouse key fixture;
   - logging keys;
   - the full existing suite must stay green unchanged (16 call sites, 5 `ip_hash is not None` integration assertions).

   **CHECKPOINT:** stop and review before going on.
   - Run `ruff`, `mypy src tests` and the **full** `pytest`.
   - Confirm sessions and audit rows from a real login carry a 64-hex hash.
   - Confirm `repr(get_settings())` shows `**********`.
   - Login p95 is **not** measured (amendment E).
   - If anything here is off, fix it before any job code exists.
4. **Rotation:** domain rule, port, store, use case, job, registry; unit, integration, concurrency and security tests.
5. **Purge:** ports, three batch deletes, use case, job, registry; integration and concurrency tests, including the reset and refresh races.
6. **Docs:** ADR-028, SRS, api-endpoints, database-design, settings-registry, plan, CONTRIBUTING, `.env.example`, README, stale references, OpenAPI regeneration, `docs/security-retention.md`, smoke list.
7. **Rebase** onto `main`; re-verify one head. Run `ruff check . && ruff format --check . && mypy src tests && pytest`. Open the PR and record the EXPLAIN measurements to do later (§4.3) in its description.

---

## 10. Design decisions (options, trade-offs, recommendation)

### 10.1 Salt storage and protection

| Option | Leak of DB alone | Leak of env alone | Leak of both | Rotation gives unlinkability? |
|---|---|---|---|---|
| A. Plan's literal design: DB salt, `sha256(salt:ip)`, env salt removed | **Reversible** (4·10⁹ IPv4 guesses per salt) | Nothing | Reversible for kept salts | Only if old salts are deleted |
| B. **HMAC keyed by derive(env pepper, DB salt)** | Nothing (pepper missing) | Nothing (salt missing) | Reversible only for salts **still stored**, i.e. the current month | Yes, once the old salt is deleted |
| C. Env-only salt rotated by redeploy | — | Reversible | — | Needs a manual secret change monthly; not a job |

**Recommendation: B.** A DB-only salt (A) sits next to the hashes in the same dump, which is exactly the leak SEC-25 guards against.

What happens to the env `IP_HASH_SALT`:
- it **stays required** and keeps its name, with a new meaning as the pepper;
- CI (`cp .env.example .env`), `.env.example`, `tests/unit/conftest.py:25`, `test_error_contract.py:23` and `test_health.py:14` need **no change**;
- it becomes `SecretStr`;
- rotating the pepper itself is an operator action, re-deriving on next refresh with no data migration.

### 10.2 Old salts: delete or keep?
- **Keep (versioned history, the plan's wording):** keeping history defeats the purpose. Anyone with history and pepper can link every month.
- **Delete after a grace window:** nothing ever reads an old salt (Q1), so a grace window buys nothing. Processes holding the old **derived key** keep working regardless, because they hold it in memory.

**Recommendation:** delete in the rotation transaction (grace 0 in the DB). In-memory staleness is bounded by `REFRESH_SECONDS = 60`.

### 10.3 `hash_ip` sync versus async

| | (a) `async def hash_ip(ip, session)` reading the salt in the request transaction | (b) **Sync, in-process cached key, 60 s lazy refresh** |
|---|---|---|
| Call-site churn | 16 sites, 3 `_audit_context` helpers, every use case test fake | None (return type widens to `str \| None`) |
| Request cost | One extra query on every hashing request (login, refresh, every admin write) | One query per process per minute |
| Staleness after rotation | 0 | ≤ 60 s (harmless, Q1) |
| DB read failure | The request fails (it would anyway) | The last key keeps working; None if never loaded |
| Unit tests (env-only) | Need a fake session everywhere | One autouse fixture installs a key |

**Recommendation: (b).**

### 10.4 "Exactly one current" and two workers
- **Partial unique index** on `(is_current) WHERE is_current` gives "at most one", enforced by the DB.
- **Advisory transaction lock** plus re-check under the lock serialises rotations.
- **Month rule** makes reruns no-ops.
- A conditional `INSERT ... WHERE NOT EXISTS` without a lock would still race on "is it due". Two workers could each delete and insert in turn, rotating twice and leaving hashes from the first rotation briefly. The lock is the simple answer and matches `ensure_partitions`.

**Recommendation:** all three together.

### 10.5 Missed runs
Daily cron plus `run_at_startup=True` plus the month rule (§2.2). After any downtime, the first run of a new month rotates exactly once. A `day=1` cron alone loses the month (Q5).

### 10.6 Purge predicates

| Table | Predicate | Why |
|---|---|---|
| verification_tokens | `expires_at < now - security_token_retention_period` | One column. Provably never live, since `expires_at < cutoff < now`. Used tokens expire at most 24 h after creation, so they are covered too. |
| password_reset_tokens | same | Same; the TTL is 1 h. |
| sessions | `expires_at < c OR revoked_at < c`, with `c = now - session_retention_period` | Live means `revoked_at IS NULL AND expires_at > now`; neither branch can match. |

For batching, locking and concurrency, see §2.3 and §5.4. For indexes, see §4.3.

### 10.7 ADR-011 compliance and monitoring
- Both jobs call use cases, not repositories. The `purge_unverified` deviation is noted (Q6) and left alone; fixing it is out of scope.
- Both jobs are registered in `jobs/registry.py`, log a structured line, and **raise** on failure.
- VS-047's per-job cron heartbeat covers them automatically.

---

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Middleware ordering: the refresh runs after a handler that hashes | Low | Register the middleware outermost after RequestID; test that a request after the TTL sees the new key. |
| `make_app` drifts from `main.py` (no middleware in tests, so tests pass on stale keys) | Medium | The rotation test goes through `make_app`; the conftest comment `:124-125` already asks to keep them in step. |
| VS-028 lands a settings migration first | Medium | The migration lock; rebase; recount the seed tests (14 + VS-028's net +2). |
| A purge deletes rows other integration tests still need | Low | Tests pin `now` in the year 2000 (§7); production retention minimum is 1 day. |
| `SKIP LOCKED` starves a permanently locked row | Very low | Rows locked for days do not occur; the next run catches them. |
| Salt echoed by a driver error | Low | Salt bytes are generated server-side; only the error class is logged; a security test (§7.4). |
| `hash_ip` returns None silently for a long time (missing row) | Low | A warning log once per minute; the startup rotation run self-heals an empty table; VS-047 alerting. |
| Old salts survive in backups | Certain (bounded) | Documented (L5); owner question 9. |

---

## 12. Owner questions (each with a recommendation)

1. **Retention values.** Tokens are deleted 7 days after `expires_at`; sessions 30 days after they end (expiry or revocation). Both are admin-editable, with a range of 1–90 days. **Recommend: yes.**
2. **Rotation rule.** Rotate on the first run of each UTC calendar month (daily check plus at worker start), rather than "every 30 days" or a `day=1` cron. **Recommend: calendar month.**
3. **Env variable name.** Keep `IP_HASH_SALT` as the name of the new pepper, or rename it to `IP_HASH_PEPPER`? A rename breaks every local `.env` and CI's copy step, as ADR-026's `CAPTCHA_PROVIDER` did. **Recommend: keep the name** and document the meaning.
4. **Old salt grace window.** Delete the previous salt in the rotation transaction (grace 0), given that nothing reads old salts and processes refresh within 60 s. **Recommend: 0.**
5. **Raw IPs and unsalted email digests in Redis keys** (L1, L2). Non-goal here. Fix them with VS-020 by keying on `hash_ip(ip)` and an HMAC of the email? **Recommend: yes, a follow-up attached to VS-020.**
6. **Audit-log 24-month retention and archiving** (SRS §21.4). Who owns it: VS-047, or a new slice? **Recommend: a new small slice after VS-047**, since archiving needs the backup target.
7. **`mfa_recovery_codes`.** Leave used codes unpurged in V1? **Recommend: yes, non-goal.** They are tiny and hold no IP data.
8. **Legacy `ip_hash` values** written with the old static salt exist only in development databases. Confirm no production or staging data exists, so no backfill is needed. **Recommend: confirm; no backfill.** If staging exists by merge time, generate a new pepper at deploy.
9. **Backups and unlinkability.** Old salts stay recoverable from backups until backup retention expires. Accept this, and have VS-047 state the backup retention? **Recommend: accept and record it in ADR-028 and VS-047.**
10. **Audit trail for jobs.** The rotation writes one audit row (ids only); the purge logs counts only, as `purge_unverified_accounts` does. **Recommend: yes.**
11. **Spec edits.** Approve the SRS §23 change (add `purge_expired_security_records`; reword the `rotate_ip_salt` cadence), the §24 secrets wording, and the VS-046 plan-entry corrections ("one current salt, old ones deleted", "pepper kept"). **Recommend: approve.**
12. **Rotation period.** Keep it a code rule (SRS fixes "Monthly") rather than a third setting. **Recommend: code rule.** The SRS fixes it, and an admin-shortened period adds no protection.
