# ADR-005: Use Profile C Clean Architecture as a modular monolith

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §18.2–§18.4; Backend OS Profile C decision

## Context

Checkout, payment verification, refunds, per-line fulfillment, entitlements, negotiation, identity, and scheduled operations contain real state machines and transactional boundaries. A flat CRUD structure would blur ownership, while microservices would add premature distributed-system cost.

## Decision

Use Profile C: one modular monolith with nine bounded contexts — Identity, Catalog, Digital Assets, Ordering, Payments, Fulfillment, Negotiation, Engagement, Platform. Each follows domain → application → infrastructure → api with inward dependencies. Contexts own implementation; top-level API only composes routers.

## Consequences

+ Explicit ownership and testable invariants
+ Domain code stays independent of FastAPI/SQLAlchemy
+ Boundaries allow later extraction if justified
- More architectural discipline than simple CRUD
- Cross-context workflows need explicit orchestration

## Alternatives rejected

- **Profile A/B flat service architecture** — Too weak for the approved domain complexity.
- **Microservices from day one** — Distributed transactions/deployment/observability cost is not justified.
- **Framework-centric routers/models/services layout** — Technical layers would obscure business ownership.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
