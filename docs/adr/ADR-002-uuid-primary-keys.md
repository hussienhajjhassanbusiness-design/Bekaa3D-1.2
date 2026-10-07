# ADR-002: Use UUID primary keys, time-ordered where available

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** database-design.md — Global Database Conventions

## Context

Identifiers cross customer, admin, audit, background-job, webhook, and future integration boundaries. Sequential integers are easy to enumerate and couple ID generation to database sequences.

## Decision

Use UUID primary keys throughout the V1 schema, preferring time-ordered UUID generation where supported. Partitioned tables use partition-aware composite primary keys when PostgreSQL requires the partition key in uniqueness.

## Consequences

+ Consistent IDs across contexts and async work
+ Non-sequential public identifiers
+ Time-ordered UUIDs improve locality versus fully random UUIDs
- Larger indexes than integer IDs
- Less convenient for manual inspection

## Alternatives rejected

- **BIGSERIAL integers** — Would require a separate public-ID strategy or expose sequence order.
- **ULID strings** — Native PostgreSQL UUID typing/tooling is preferred.
- **Mixed ID types** — Inconsistency is not justified at expected V1 scale.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
