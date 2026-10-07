# ADR-007: Version the REST API from day one and isolate admin routes

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §22.1–§22.4; api-endpoints.md

## Context

Storefront/admin clients depend on API paths, response shapes, and stable error codes. Admin operations need stronger authentication/MFA/rate-limit policy than public/customer operations.

## Decision

Expose V1 under `/api/v1`. Keep Authentication, Public, Customer, Admin, and Webhook groups explicit. Mount admin routes on a separate aggregated router. Use stable machine-readable error codes and RFC 9457 problem responses.

## Consequences

+ Breaking V2 can coexist with V1
+ Clear privileged security boundary
+ Stable client contracts
- Future versions may temporarily duplicate contracts

## Alternatives rejected

- **Unversioned API** — Breaking changes would force synchronized client deployment.
- **Header-only versioning** — Path versioning is simpler to route, document and operate here.
- **Mixed admin/public router** — Weakens the privileged boundary.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
