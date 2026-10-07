# ADR-013: Centralize cross-context technical integrations behind shared ports

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §18.4; frozen src architecture

## Context

Storage is needed by Catalog, Digital Assets and Engagement; scanning by Digital Assets and Engagement; email/captcha cross context boundaries. Reimplementing provider clients in each context would make provider changes touch many modules.

## Decision

Define shared technical ports/adapters for storage, email, captcha and malware scanning. Context application logic depends on these ports while retaining its own business rules. Concrete local/S3, email, captcha and ClamAV implementations are shared. Payment remains Payments-owned because it is a domain-specific provider boundary.

## Consequences

+ One provider implementation can be replaced centrally
+ Consistent security behavior across contexts
+ Business ownership remains in contexts
- Shared technical packages must stay generic and avoid business leakage

## Alternatives rejected

- **Duplicate clients per context** — Provider replacement and security fixes would be repeated N times.
- **Move all file business logic into shared code** — Would steal domain rules from the owning contexts.
- **Genericize payment too** — Payment is explicitly owned by Payments.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
