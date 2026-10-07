# ADR-001: Use PostgreSQL 16 as the primary database

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §18.1, §21; database-design.md

## Context

Bekaa3D has strongly relational, transaction-heavy workflows: mixed carts/orders, per-line fulfillment, payments, refunds, entitlements, offers, translations, audit history, and reporting. Important invariants must survive concurrency and are naturally enforced with foreign keys, checks, partial unique indexes, row locks, and transactions.

## Decision

Use PostgreSQL 16 as the system of record for transactional application data. Use SQLAlchemy 2 async and Alembic. Redis is infrastructure for queue/cache/rate limits, never a second source of transactional truth.

## Consequences

+ Strong ACID transactions and relational constraints
+ PostgreSQL search/index/partition features fit the frozen schema
+ Mature reporting SQL and recovery tooling
- PostgreSQL-specific features reduce database portability
- Requires disciplined migration/operations knowledge

## Alternatives rejected

- **MongoDB** — Core data/invariants are relational and transactional.
- **MySQL** — Viable relationally, but the frozen design intentionally uses PostgreSQL-specific partial indexes, search and partitioning.
- **Database per bounded context** — Adds distributed consistency and operations cost without a V1 need.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
