# ADR-009: Preserve business history with soft deletion and anonymisation

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS BR-018, §14.5; database-design.md

## Context

Financial, order, refund, entitlement, offer and audit history must remain trustworthy after products/users leave the active system, while temporary/security/retention-managed records must still expire.

## Decision

Soft-delete core mutable business records where history/references must survive. Verified-account deletion anonymises rather than purges and retains required financial/download history. Physical purge is limited to explicitly retention-managed data such as expired tokens, stale unverified accounts, temporary attachments and expired partitions/details.

## Consequences

+ Preserves accounting/audit/referential history
+ Supports deletion without breaking orders
+ Makes retention exceptions explicit
- Queries must consistently exclude deleted rows
- Partial unique indexes/anonymisation flows add complexity

## Alternatives rejected

- **Hard-delete business history** — Destroys accounting/audit/reference integrity.
- **Never physically delete anything** — Conflicts with token/upload/log retention requirements.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
