# ADR-016: Launch V1 English-only

**Status:** Accepted
**Date:** 2026-08-12
**Supersedes:** ADR-010
**Source basis:** SRS (revised scope); project-brief.md budget and timeline constraints

## Context

ADR-010 committed to a bilingual Arabic+English launch with per-locale translation tables, locale-aware slugs, Arabic search normalization, and full RTL layout. project-brief.md classifies Bekaa3D as a Profile C (complex backend) system on a severely constrained budget (~USD 2,500–3,000) and a three-person team. The SRS itself flagged bilingual launch as a high-severity risk: it materially increases schema complexity, search complexity, frontend RTL effort, content-authoring burden, and QA surface, without a confirmed demand signal requiring Arabic at V1 launch.

The SRS, domain glossary, entities-and-business-rules.md, functional-requirements.md, non-functional-requirements.md, and project-brief.md have already been revised to scope V1 as English-only. This ADR records the resulting architecture and schema consequence, and formally supersedes ADR-010 rather than editing it.

## Decision

V1 ships English-only. Catalogue text lives in plain columns on the owning table instead of per-locale translation tables:

- `Product.name`, `Product.description`, `Product.slug`, `Product.seo_title`, `Product.seo_description`
- `Category.name`, `Category.slug`
- `Material.name`
- `Colour.name`

No `ProductTranslation`, `CategoryTranslation`, `MaterialTranslation`, or `ColourTranslation` tables. No `locale` column anywhere. Slug uniqueness is enforced among non-deleted rows globally, not per-locale. Full-text search uses only the built-in `english` text-search configuration; there is no Arabic normalization function, no `simple`-configuration branch, and no dual-language `tsvector`. There is no language switcher, no `hreflang`/per-language SEO metadata, no RTL layout requirement, and no missing-translations report.

This was a deliberate choice between two options considered during the SRS revision: collapsing to plain columns now, versus keeping the translation-table shape but populating only an `en` row per entity. Plain columns won because it matches the stated scope literally and removes schema/query overhead that would otherwise buy nothing until a second language is actually approved.

## Consequences

+ Simpler schema: fewer joins, no per-locale slug uniqueness index, no fallback-resolution logic in queries
+ Smaller QA and content-authoring surface for a team and budget that cannot absorb bilingual QA
+ No RTL/bidirectional-text frontend work
+ Faster to build within the phased Profile C budget in project-brief.md
- Adding a second language later is a real schema migration (introducing translation tables or locale columns) plus a content backfill, not a row-insert
- Any catalogue content authored in V1 must be reshaped, not just supplemented, if bilingual support is added later

## Alternatives rejected

- **Keep ADR-010's translation tables, populate only the `en` locale** — Keeps join/query overhead and an unused `locale` column live in every catalogue read path for a language that isn't shipping. Rejected in favor of plain columns.
- **Proceed with the original bilingual launch as ADR-010 specified** — Rejected: the SRS's own risk register rated this high-severity against project-brief.md's budget and timeline constraints, with no confirmed Arabic-speaking-customer demand data justifying the cost at V1.

## Revisit when

Revisit if the business collects demand data that justifies Arabic support, or if budget/timeline headroom opens up enough to absorb bilingual schema, search, content, and RTL QA cost as a dedicated phase — treat it as adding a new context-wide capability, not a small patch on top of the plain-column schema.
