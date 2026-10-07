# ADR-015: Partition downloads and audit logs by month

**Status:** Accepted; the `downloads` half superseded by [ADR-019](ADR-019-manual-stl-delivery.md) (no downloads table). Audit-log partitioning stands.  
**Date:** 2026-08-10  
**Source basis:** SRS §21.4, §23; database-design.md

## Context

Downloads and audit logs are append-heavy and have retention/archive policies. These tables need predictable maintenance as they grow.

## Decision

Use monthly range partitions for `downloads` by `started_at` and `audit_logs` by `created_at`. Pre-create partitions three months ahead via a mandatory scheduled job. Keep raw download detail 24 months with monthly aggregates indefinitely; keep audit data hot 24 months before archive per the frozen design.

## Consequences

+ Efficient retention/archive by partition
+ Smaller operational working sets
+ Easier maintenance of append-heavy data
- Partition creation becomes an operational dependency
- PostgreSQL partition-key uniqueness rules complicate PKs

## Alternatives rejected

- **Single unpartitioned tables** — Retention/maintenance cost grows continuously.
- **Partition every table** — Unnecessary operational complexity.
- **Immediate external archive database** — Too complex for V1.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
