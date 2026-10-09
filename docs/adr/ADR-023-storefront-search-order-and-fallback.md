# ADR-023: Rank storefront search by relevance, fall back to trigram below five hits, and pin the mode in the cursor

**Status:** Accepted (amended 2026-10-08 after the VS-016 audit: decisions 2, 3, 4 and 6, and the consequences)
**Date:** 2026-10-08
**Source basis:** SRS §6.3, §6.4, §21.3, §21.5, FR-01 (failure behaviour, concurrent access), NFR-02, SEC-24; database-design.md §18; vertical-slice-plan VS-016
**Applies first to:** `GET /api/v1/products?q=` and `GET /api/v1/search/suggestions` (VS-016)

## Context

SRS §21.5 says names are weighted above descriptions in the search vector. That weight only shows in a ranked result, but §6.4 lists only price, rating and newest as sorts. §6.3 and FR-01 say to fall back to trigram similarity "when results are thin", and the slice plan sets the threshold at five full-text hits. The storefront list is keyset-paginated, and FR-01 requires that catalogue changes never make a record repeat or vanish within a paginated sequence. A fallback decided again on every page breaks that: if a product added mid-walk lifts full-text hits past five, the trigram matches already promised on page one disappear from page two.

pg_trgm's default `word_similarity` threshold is 0.6. Measured on PostgreSQL 16 against real product names, that misses single-letter typos such as `plnter` for "Self-watering Planter" (0.50) and `lamb` for "Moon Lamp" (0.60, exactly at the boundary).

## Decision

1. **A search orders by relevance by default.** With `q`, `sort` defaults to `-relevance`. Without `q`, `-relevance` is a 422. The explicit sorts still apply to a search.
2. **Relevance** is one double: `2 + ts_rank(search_vector, websearch_to_tsquery('english', q))` for a full-text hit, otherwise `word_similarity(q, name)` (at most 1). Full-text hits therefore always rank strictly above trigram-only ones, and the stored A/B weights rank a name hit above a description hit. Ties break on `id`, like every other sort. The offset was 2 because a negation-only query such as `-lamp` ranks 0; since decision 3 keeps negated queries out of the fallback, 1 would now do, and 2 is kept as margin.
3. **Fallback.** The first page counts the full-text hits, with the facets applied, stopping at five. Below five, the result set is full-text hits **or** names with `word_similarity >= 0.5`. Trigram matches add to the full-text hits and never replace them. The fallback applies only when the term contains **a word of at least 3 letters or digits** and **excludes no word**. Words are counted as pg_trgm reads them, so `s s`, `(s)` and `s!!` are still one letter. Shorter terms match every name with a word starting with those letters, which costs a similarity score per row: `q=s` took 420-690 ms on 10,000 products and failed NFR-02 in CI. An exclusion is whatever PostgreSQL parses as a NOT: a `!` outside the lexemes of `websearch_to_tsquery`'s output, so `lamp -moon`, `lamp - moon` and `(-moon)` all count. Trigrams ignore operators, so falling back would bring the excluded word straight back (`lamp -moon` returned only "Moon Lamp"). This deliberately narrows FR-01's failure behaviour ("trigram similarity is used as a fallback"): it was an owner decision after the VS-016 audit.
4. **The cursor pins the mode** (`full_text` or `fuzzy`) chosen by the first page. A search cursor is refused without `q`, and a browse cursor is refused with `q`. A `fuzzy` cursor whose `q` is not eligible for the fallback (decision 3) is refused too, so a forged cursor can't reopen it.
5. **Threshold 0.5,** set per transaction with `set_config('pg_trgm.word_similarity_threshold', '0.5', true)` so it never leaks to another request on a pooled connection. The `<%` operator, not the `word_similarity()` function, does the filtering, so the GIN trigram index serves it.
6. Autocomplete uses the same trigram predicate, ordered by `word_similarity` descending, then name, then `id`, at most ten. It needs a word of at least 3 letters or digits, like the fallback.

## Consequences

- A search without a word of three letters or digits gets full text only, so `sp` finds nothing until a third letter is typed, and autocomplete waits for three letters too.
- A search that excludes a word gets no typo tolerance: `lmap -moon` finds nothing, rather than risk returning what was excluded.
- One deleted, substituted or inserted letter is found. A transposition (`dargon`, 0.29) is not: trigrams treat it as two edits. This is accepted for V1.
- Relevance is recomputed on every page. Because it is deterministic for the same row and query, the keyset stays exact. If an administrator edits a product's name or description mid-walk, its rank changes and it can cross the cursor. This is the same accepted limit as a price change under a price sort (docs/storefront-catalogue.md).
- A cursor isn't bound to the `q` text. Reusing one with a different `q` only changes where the walk starts, and it can't leak a row the new query wouldn't match.

## Alternatives rejected

- **No relevance sort:** this leaves the §21.5 weighting with no observable effect, and gives a visitor's search results in newest-first order.
- **Deciding the fallback on every page:** this breaks FR-01's pagination guarantee as described above.
- **Raising the threshold globally** (`ALTER DATABASE ... SET`): the setting would be hidden in database state that migrations and fresh environments don't carry.
