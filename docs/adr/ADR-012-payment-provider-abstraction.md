# ADR-012: Use a payment-provider abstraction and independently verify payment

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS BR-052–BR-058, §9.1–§9.4

## Context

Whish is V1's provider, but provider details can change. Callbacks can be forged/retried and lost callbacks can leave customers charged without fulfillment.

## Decision

Keep payment interaction behind a Payments-owned provider port with mock and Whish adapters. Persist/idempotently identify callbacks, verify signatures where supported, independently verify provider status and exact amount before marking paid or granting/producing anything, and run reconciliation. Provide a manual admin confirmation fallback only when automatic verification is unavailable.

## Consequences

+ Provider details stay isolated
+ Forged callbacks cannot grant goods
+ Lost callbacks are recoverable
+ Future provider replacement is bounded
- More payment states/operational paths
- Manual fallback may be slower

## Alternatives rejected

- **Trust callback as payment proof** — Critical security failure.
- **Call Whish directly from order/checkout code** — Creates high coupling and poor testability.
- **Grant before verification** — Risks unpaid files/production.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
