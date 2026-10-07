# ADR-008: Represent money as integer cents with explicit currency

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS BR-051, §22.1; database-design.md

## Context

Product prices, offers, shipping, totals, payments and refunds must reconcile exactly. Binary floating point can introduce rounding errors.

## Decision

Store money as integer cents (`BIGINT`) plus explicit currency. V1 currency is USD. API money uses `amount_cents` and `currency`. Never use binary floating point for monetary logic.

## Consequences

+ Exact deterministic arithmetic
+ Exact payment amount comparison
+ Safe refund/subtotal calculations
- Presentation must format minor units for display

## Alternatives rejected

- **float/double** — Cannot represent many decimal currency values exactly.
- **Formatted strings** — Poor for arithmetic/validation/reporting.
- **Decimal everywhere** — Viable, but integer minor units are simpler for the V1 payment contract.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
