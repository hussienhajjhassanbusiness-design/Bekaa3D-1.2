# ADR-010: Use separate translation tables for bilingual content

**Status:** Superseded by [ADR-016](ADR-016-english-only-v1.md)  
**Date:** 2026-08-10  
**Source basis:** SRS §17.1–§17.4, §21.5

## Context

Arabic and English launch together. Products/reference data need per-locale names, descriptions, SEO metadata, slugs, fallback behavior, missing-translation reporting, and locale-aware search.

## Decision

Use separate translation tables keyed by entity and locale instead of JSON translation blobs. Enforce live per-locale slug uniqueness relationally. Product names are required in both languages; longer fields use the approved fallback policy.

## Consequences

+ Enforceable locale slug uniqueness
+ Straightforward search/index/reporting
+ Translation gaps are queryable
- More joins and rows than embedded JSON

## Alternatives rejected

- **JSONB translation objects** — Makes per-locale relational uniqueness/reporting less direct.
- **Duplicate full entity per language** — Duplicates non-translatable business data.
- **Single-language canonical fields** — Does not satisfy bilingual launch requirements.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
