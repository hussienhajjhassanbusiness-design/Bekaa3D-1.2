# ADR-003: Keep V1 single-tenant

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §1, §18; V1 architecture freeze

## Context

V1 serves one Bekaa3D business with one catalogue, admin domain, settings set, merchant configuration, and fulfillment operation. The approved SRS does not require SaaS tenant isolation.

## Decision

Do not add tenant IDs, tenant schemas, or database-per-tenant infrastructure in V1. A future SaaS/multi-business conversion requires a new ADR and explicit migration/isolation plan.

## Consequences

+ Keeps every context/schema simpler
+ Avoids tenant-scope authorization mistakes
+ Matches current requirements
- Future SaaS conversion would be a significant change

## Alternatives rejected

- **tenant_id on most tables** — Adds pervasive complexity for a requirement that does not exist.
- **Schema per tenant** — Adds provisioning/migration complexity.
- **Database per tenant** — Multiplies deployment, backup and connection operations.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
