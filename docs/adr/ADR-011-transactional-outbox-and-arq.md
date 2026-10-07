# ADR-011: Use a transactional outbox and durable scheduled arq jobs

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §16.2, §18.1, §23, §24.1

## Context

Critical work continues after HTTP transactions: verification/order/payment email, offer expiry, stale checkout release, reconciliation, retention cleanup, partition maintenance, download aggregation and backup checks. External delivery failures must not roll back business state.

## Decision

Insert email/outbox work in the same PostgreSQL transaction as the triggering business change. Deliver with arq. Use Redis plus dedicated worker/scheduler entrypoints for deferred and cron jobs. Job entrypoints call application use cases rather than embedding business logic/raw SQL.

## Consequences

+ Durable post-commit work
+ Recoverable email/provider outages
+ Explicit monitored scheduling
+ API and jobs reuse the same application/domain logic
- Requires Redis, worker and scheduler operations
- Jobs must be idempotent and monitored

## Alternatives rejected

- **Send email inside request transaction** — Couples business success to external email latency/failure.
- **FastAPI BackgroundTasks for critical work** — Not durable across process failure.
- **Manual scripts only** — Does not satisfy standing scheduled/reconciliation requirements.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
