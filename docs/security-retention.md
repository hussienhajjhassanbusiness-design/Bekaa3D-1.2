# Security data retention and IP-hash rotation (VS-046)

Operator notes for the two jobs VS-046 adds. The decision record is [ADR-028](adr/ADR-028-keyed-monthly-rotated-ip-hashes.md), and the full plan is [`plans/VS-046-security-retention-plan.md`](plans/VS-046-security-retention-plan.md).

## What is purged, and when

`purge_expired_security_records` runs daily at 03:29 UTC.

| Table | Deleted once | Default | Setting |
|---|---|---|---|
| `verification_tokens` | `expires_at` is older than the retention, whether the token was used or not | 7 days | `security_token_retention_period` |
| `password_reset_tokens` | as above | 7 days | `security_token_retention_period` |
| `sessions` | the session **ended** longer ago than the retention. The end is the earlier of `expires_at` and `revoked_at`. | 30 days | `session_retention_period` |

- **Live rows are never deleted.** A live session has no `revoked_at` and an `expires_at` in the future, and every cutoff is in the past.
- **Users see one change.** While an expired verification or reset link's row exists, the link answers `410 RESOURCE_EXPIRED`. After the purge it answers `400 INVALID_TOKEN`.
- **Refresh is unchanged.** A purged session answers refresh with the same `401` as a revoked one.
- **How it runs.** The job deletes in batches of 1000 rows, each its own short transaction using `FOR UPDATE SKIP LOCKED`, so it never waits on a login, a refresh or a reset.
  - It stops after 50 batches per run and logs `truncated=true`. The next day continues.
  - It logs `security_records_purged` with counts only, and writes no audit row.

## Changing the retention

Both settings are admin-editable, from 1 to 90 days, in seconds (BR-133):

```http
PATCH /api/v1/admin/settings/session_retention_period
{"value": 1209600}
```

The job reads both values at the start of each run, with **no fallback**. If a stored value is missing or invalid, the run fails before deleting anything.

## IP-hash rotation

`rotate_ip_salt` runs daily at 00:23 UTC and at every worker start.

- **When it rotates.** It replaces the salt when the current one predates the current UTC month, so it rotates once a month and catches up after downtime.
- **What it changes.** The old salt is deleted in the same transaction, and one `ip_hash_salt.rotated` audit row records the old and new ids.
- **Safety.** Any number of workers may run it at once.
- **If it fails.** The job raises, arq marks it failed, and the old salt stays current. The next daily or startup run retries. One cause is a missing `audit_logs` partition for the current month, which `ensure_partitions` normally prevents.
- **Pickup delay.** API processes pick up the new salt within about 60 s.
- **The pepper.** The other secret is `IP_HASH_SALT` in the environment. Changing it needs a process restart.

## Known limitations

| # | Limitation | Status |
|---|---|---|
| L1 | Raw client IPs appear in Redis rate-limit and login-throttle keys (TTL at most 1 h) | Follow-up with VS-020 |
| L2 | Redis keys use an unsalted `sha256(email)[:32]`, which a dictionary can reverse | Same follow-up |
| L3 | Audit logs are kept hot for 24 months and archived (SRS §21.4); not implemented | Separate slice |
| L4 | Used `mfa_recovery_codes` rows are never purged (no IP data, at most 10 per regeneration) | Accepted for V1 |
| L5 | Backups keep old salts until backup retention expires | Recorded in ADR-028; VS-047 |
| L6 | Hashes written up to about 60 s after a rotation use the previous key | Accepted |
