# ADR-014: Use first-class entitlements and nginx-protected STL delivery

**Status:** Superseded by [ADR-019](ADR-019-manual-stl-delivery.md)  
**Date:** 2026-08-10  
**Source basis:** SRS §10.2–§10.6, §24.3

## Context

Digital access may come from purchase, accepted offer or admin grant and may be revoked by refund/chargeback. STL bundles are versioned and must never be publicly reachable by guessable paths.

## Decision

Entitlement is the sole authority for STL access, with at most one active entitlement per user/product. Keep STL masters private with generated storage names. Authorize each download, enforce abuse limits, write a log, then return nginx `X-Accel-Redirect`; nginx transfers bytes with Range support. Asset-version supersession is atomic.

## Consequences

+ One grant/revoke authorization model
+ Secure private delivery
+ Python workers do not stream large files
+ Versioning is independent of entitlement
- Requires nginx/storage coordination
- Downloaded bytes cannot be recalled after revocation

## Alternatives rejected

- **Check orders directly for every download** — Does not cover every grant/revoke source cleanly.
- **Public/static STL URLs** — Bypasses entitlement authorization.
- **Stream through FastAPI** — Consumes API/event-loop capacity.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
