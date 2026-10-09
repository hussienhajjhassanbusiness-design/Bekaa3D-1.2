# VS-016 audit: search and autocomplete

This is an independent, read-only audit, dated 2026-10-08. The audited tree is branch `main` @ `0b1909a` ("VS-016: search and autocomplete (#4)"), which was clean. No source, test, migration or status file was changed. Mutations and probes ran only on `git archive HEAD` copies in the session scratchpad, outside the repo.

## 1. Verdict

**Not yet. Fix one thing first.** The search logic is sound. It ships English full text with stemming, a trigram fallback below five hits counted inside the facets, a relevance order, the fallback mode pinned in the cursor, a transaction-local threshold, bound parameters throughout, visibility in both modes and in suggestions, and a separate rate-limit counter. 31 of 34 mutations are killed outright.

The blocker is the slice's own "Done when: search p95 < 800 ms" line. **CI on `main` is red.** Run 37783074634 failed `test_search_p95_is_under_800_ms_on_10k_products` with *p95 1004 ms over 96*. The cause is a single query shape: a one-letter search (`q=s`) puts every name into the trigram fallback and takes 420–690 ms locally (A-01). Every later slice's PR will run that test, so fix A-01 before VS-020.

The other gaps are in test strength:

- SRS §21.5 says a name match outranks a description match. That rule is guarded by a coin flip (A-02).
- The suggestion "closest first" test passes by alphabetical accident (A-03).
- Neither the order of trigram-only hits nor the upper bound of the threshold is pinned (A-04, A-05).
- `pytest -m smoke` does not select any of the VS-016 tests it claims to (A-06).

## 2. Repo state (Phase 1)

| Item | Finding |
|---|---|
| Current branch | `main` @ `0b1909a129ce556d35ae6af881fe094e86d468ae`, same as `origin/main` |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only untracked file is this report |
| VS-016 on `main`? | Yes: squash-merge `0b1909a` (PR #4); 24 files, +1235/−90. There is no migration (`git diff 6399fbc 0b1909a -- migrations` is empty) |
| Commits touching the slice's files | `0b1909a` (all of them). `6399fbc` (VS-015) created the shared files `storefront.py`, `storefront_query.py`, `product_cursor.py` and `domain/storefront.py` |
| CI | PR head `ac4cb43`: success. **Merge commit `0b1909a` on `main`: failure** (see §3) |

## 3. Command results (Phase 2)

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 428 files already formatted |
| `mypy src tests` (strict) | PASS | 368 source files, no issues |
| `pytest` (full) | PASS | **2011 passed, 1 skipped, 5 deselected (`timing`), 0 xfailed, 0 failed**, 21 min 36 s. The skip is `test_clamav_adapter.py:91` (no clamd on 127.0.0.1:3310), which is unrelated |
| `pytest -m integration` | PASS | 1458 passed, 559 deselected, 22 min 06 s (it ran alongside the mutation runs, so the p95 tests passed under load locally) |
| `pytest -m concurrency` | PASS | 89 passed, 1928 deselected, 2 min 22 s |
| `pytest -m smoke` | PASS, but incomplete | 78 passed. **The only VS-016 item selected is `test_every_listed_vs016_smoke_test_still_exists`**; none of the 7 tests it lists are marked smoke (A-06) |
| `alembic heads` | PASS | Exactly one head: `cc87333ebe79`. VS-016 has no migration, so there is no upgrade/downgrade cycle to run. Its indexes (`ix_products_search_vector`, `ix_products_name_trgm`) come from VS-013 `fc18b48a1780:141-149` |
| **GitHub Actions on `main` (`0b1909a`)** | **FAIL** | `gh run view 37783074634`: `FAILED tests/integration/catalog/test_storefront_scale.py::test_search_p95_is_under_800_ms_on_10k_products - AssertionError: p95 1004 ms over 96`; 1 failed, 2010 passed |

Every xfail recorded in the VS-010 audit has since been resolved. The suite has none.

## 4. Requirement checklist (Phase 3)

Sources: the slice section of `vertical-slice-plan.md`; SRS §6.3, §6.4, §6.5, §21.3, §21.5, F-007, F-010, NFR-02 and SEC-24; FR-01 (functional-requirements.md:16-67); database-design.md §18; api-endpoints.md lines 225-241; ADR-023.

| Requirement | Status | Code | Test that proves it |
|---|---|---|---|
| GIN on `search_vector`, GIN trigram on `name` (§21.3) | DONE (VS-013) | `fc18b48a1780_products_table.py:141-149` | `test_search_plans_use_the_gin_indexes[full_text/fuzzy/suggestions]` (M32 red) |
| Generated `tsvector`, `english`, name weight A over description weight B (§21.5, §18.1) | DONE (code) / PARTIAL (test) | `fc18b48a1780:39-42`; `ts_rank` at `storefront_query.py:89-98` | `test_a_name_match_ranks_above_a_description_match_above_a_near_miss`, which catches M09 only 2 times in 8 (A-02) |
| Snowball stemming via `english` (§6.3) | DONE | `storefront_query.py:53,79-81` | `test_exact_and_stemmed_queries_match[dragons, articulating]`, `test_descriptions_are_searched_too` (M14 red) |
| Search over names **and** descriptions (F-007, FR-01) | DONE | `search_vector` covers both | `test_descriptions_are_searched_too` (M11, M14 red) |
| `q` on `GET /products`, trimmed, blank means no search, 1–200 chars | DONE | `storefront.py:169-201`; `domain/storefront.py:40-51, 79-84` | `test_a_blank_search_is_a_plain_browse`, `test_bad_search_input_is_a_validation_error`, `test_the_maximum_length_search_is_accepted` (M18, M31 red) |
| Trigram fallback below 5 full-text hits (§6.3, FR-01 failure behaviour) | DONE | `domain/storefront.py:28,36-37`; `storefront_query.py:101-102,171-178` | `test_trigram_matches_join_in_only_below_five_full_text_hits` and the unit boundary test (M03, M05, M30 red) |
| Fallback count respects facets (ADR-023 §3) | DONE | `storefront_query.py:176` | `test_the_fallback_counts_only_hits_inside_the_facets` (M04 red) |
| A one-typo query finds the product (**Done when**) | DONE | threshold 0.5, `storefront_query.py:52,191-194` | `test_one_typo_finds_the_product[deletion/substitution/insertion/multi-word/at-threshold]` (M01, M16, M33 red) |
| Threshold is transaction-local (ADR-023 §5) | DONE | `storefront_query.py:191-194,215-216,222` | `test_the_trigram_threshold_ends_with_its_transaction` (M17 red) |
| Threshold not looser than 0.5 (precision) | PARTIAL | `storefront_query.py:52` | No test bounds it from above; M15 (0.3) survives (A-05) |
| Relevance order by default with `q`; `-relevance` without `q` is 422 (ADR-023 §1) | DONE | `domain/storefront.py:54-58` | `test_relevance_is_the_default_order_of_a_search`, `test_relevance_without_a_search_is_refused`, HTTP 422 cases (M27, M28 red) |
| Full-text hits outrank trigram-only hits, even at rank 0 (ADR-023 §2) | DONE | `storefront_query.py:95-97` (offset 2) | `test_a_full_text_hit_outranks_a_trigram_match_even_at_zero_rank` (M08 red) |
| Trigram-only hits ordered by `word_similarity` (ADR-023 §2) | PARTIAL | `storefront_query.py:96` | No test with two trigram-only hits; M10 survives (A-04) |
| Search combines with facets (§6.4, **plan test**) | DONE | `storefront_query.py:105-122` | `test_search_combines_with_facets` (full text and fuzzy) |
| Visibility: hidden, deleted, disabled or archived category excluded in both modes and in suggestions (§6.5, FR-01 negative) | DONE | `_VISIBLE` in `_base`, `full_text_hits_statement` and `suggestions_statement` | `test_search_never_returns_invisible_products[mode×how]`, `test_hiding_a_product_drops_it_from_search_and_suggestions` (M05, M06 red) |
| All queries parameterised (SEC-24, **plan test**) | DONE | `literal(term, Text)` at `storefront_query.py:75-76`; `websearch_to_tsquery` never raises | `test_injection_strings_are_inert` (M12, M13 red) |
| Cursor pagination stays stable under inserts; the mode is pinned (FR-01 concurrency, ADR-023 §4) | DONE | `storefront.py:196-215`; `product_cursor.py:176-252` | `test_search_paging_keeps_its_mode_when_inserts_flip_the_threshold` (uses `meet_or_fail`), `test_search_pages_through_every_match_exactly_once` over 5 sorts (M07, M29, M34 red) |
| An invalid cursor or unsupported sort is rejected (FR-01 negative) | DONE | `product_cursor.py:205-209, 240-242` | `test_bad_search_input_is_a_validation_error` (cursor kinds, NaN), unit tamper tests (M25, M26 red) |
| `GET /search/suggestions`: public, at most 10, `q` 2–200, 422 on bad input (F-010) | DONE | `search.py:37-53`; `suggestions_statement` `.limit` | `test_suggestions_are_capped_at_ten`, `test_bad_suggestion_input_is_a_validation_error`, `test_suggestions_need_no_account` (M19, M20, M21 red) |
| Suggestions are typo tolerant (F-010) | DONE | `_fuzzy` + threshold | `test_a_partial_or_one_typo_name_is_suggested` (M02 red) |
| Suggestions closest first | PARTIAL | `storefront_query.py:187-188` | `test_the_closest_name_is_suggested_first` passes even without the similarity order (M22 survives, A-03) |
| Suggestions have their own rate-limit counter (600/h/IP) | DONE | `search.py:25-29,40` | `test_each_route_refuses_past_its_limit_and_leaves_the_other_open[suggestions]` (M23, M24 red) |
| **Done when: search p95 < 800 ms on 10,000 products (NFR-02)** | **FAILED in CI** | `q=s` takes 420–690 ms locally (A-01) | `test_search_p95_is_under_800_ms_on_10k_products` (passes locally at 482–526 ms; **failed on `main` CI at 1004 ms**) |
| FR-01 failure: a DB outage returns a structured service error | Inherited (VS-001) | global handler | Not VS-016 scope |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, or the slice states there is none; one head | Met | The plan says "No migration"; single head `cc87333ebe79` |
| Rules in the owning context; other contexts only via ports | Met | Everything is in Catalog; the only cross-context import is `app.identity.public.not_found_error`. `tests/unit/test_deep_architecture.py` passes in the full run |
| Auth, verified email, ownership 404, admin boundary, CSRF, rate limits | Met / n/a | Public GET routes, so there is no session, CSRF or IDOR (`test_public_reads_need_no_session_and_never_answer_401`). Rate limit per route (A-01 is not about the limiter) |
| Money in cents; UTC; server computes status | n/a | Read-only, no money |
| Audit/notification/outbox in the same transaction | n/a | Read-only |
| Background jobs | n/a | None |
| Unit, PG integration, API error and concurrency test per race | Met | Unit (`test_storefront.py`, `test_product_cursor.py`), PG integration (search, suggestions, scale), 422/429 API tests, and a concurrency test for the one known race (fallback flips mid-walk) using `meet_or_fail` |
| Each "Done when" covered; ruff, mypy and pytest **green in CI** | **Not met** | Both "Done when" lines have tests, but **CI on `main` failed** on the NFR-02 test (A-01). Also, the wall-clock assertion runs in the default suite (A-08) |
| Docs and OpenAPI updated; Status Done | Partly | `storefront-catalogue.md`, ADR-023, api-endpoints.md (422 correction, `-relevance`), README and plan Status are all updated. OpenAPI (probed): `sort` enum includes `-relevance`, suggestions `q` is required, `limit` is 1..10, and 422/429 are documented. The README's "search p95 56 ms" does not match the test's own shapes (482–526 ms locally; A-01). The smoke-suite docstring claims wiring that does not exist (A-06) |
| Glossary naming | Met | `search_vector`, `SearchSuggestion`, `ProductType`; no synonyms |

## 6. Findings

**Mutation results (Phase 4).** Each mutation was applied alone on a scratch copy and then reverted. Target set: `tests/unit/catalog`, `test_storefront_search.py`, `test_search_suggestions.py`, `test_storefront_products.py`, `test_storefront_rate_limit.py`, `tests/concurrency/test_storefront_search_cursor.py`, plus `test_storefront_scale.py` for M01, M02, M32 and M33. Baseline: 315 passed (306 without the scale file). All 34 mutations ran twice. M09 gave different results across the two runs, so it was repeated 8 more times.

| Mutation | Result (killing tests) |
|---|---|
| M01 list fuzzy: skip the threshold `set_config` (pg_trgm default 0.6) | RED: `test_one_typo_finds_the_product[at-threshold]` |
| M02 suggestions: skip the threshold `set_config` | RED: `test_a_partial_or_one_typo_name_is_suggested[substitution]` |
| M03 fallback boundary `>= 5` → `> 5` | RED: unit boundary, `test_trigram_matches_join_in_only_below_five_full_text_hits`, concurrency test |
| M04 fallback count ignores facets | RED: `test_the_fallback_counts_only_hits_inside_the_facets` |
| M05 fallback count ignores visibility | RED: `test_trigram_matches_join_in_only_below_five_full_text_hits` |
| M06 suggestions ignore visibility | RED: 9 tests (`test_search_never_returns_invisible_products[*]`, `test_hiding_…`) |
| M07 cursor mode ignored (fallback re-decided per page) | RED: `test_search_paging_keeps_its_mode_when_inserts_flip_the_threshold` |
| M08 relevance offset 2 → 1 | RED: `test_a_full_text_hit_outranks_a_trigram_match_even_at_zero_rank` |
| **M09 relevance drops `ts_rank` (every full-text hit ties)** | **FLAKY: red in 3 of 10 runs (1 of 2 full runs, 2 of 8 repeats)**. Ties fall to `id DESC` on random UUIDs |
| **M10 trigram-only hits all score 0 (no `word_similarity` order)** | **GREEN (survives)** |
| M11 fuzzy mode drops the full-text branch of the OR | RED: 3 tests (`test_descriptions_are_searched_too`, …) |
| M12 term string-interpolated into SQL | RED: 4 × `test_injection_strings_are_inert` |
| M13 `websearch_to_tsquery` → `to_tsquery` | RED: 9 tests |
| M14 `english` → `simple` config | RED: `test_descriptions_are_searched_too` |
| **M15 threshold 0.5 loosened to 0.3** | **GREEN (survives)** |
| M16 threshold tightened to 0.6 | RED: `[at-threshold]`, suggestion `[substitution]` |
| M17 threshold session-wide (`is_local` false) | RED: `test_the_trigram_threshold_ends_with_its_transaction` |
| M18 max-length check dropped | RED: 4 tests |
| M19 suggestion minimum 2 → 1 | RED: `test_bad_suggestion_input_is_a_validation_error[one-letter]` |
| M20 suggestions `le=10` → `le=100` | RED: `[limit-11]` |
| M21 suggestions statement drops `LIMIT` | RED: `test_suggestions_are_capped_at_ten` |
| **M22 suggestions not ordered by similarity (name, id only)** | **GREEN (survives)** |
| M23 suggestions rate limit removed | RED: rate-limit `[suggestions]` |
| M24 suggestions share the list's counter | RED: rate-limit `[list]`, `[suggestions]` |
| M25 search/browse cursor kind not checked | RED: 3 tests |
| M26 relevance cursor accepts negative keys | RED: `test_a_key_of_the_wrong_kind_is_refused[-relevance--0.5]` |
| M27 search default sort stays `-created_at` | RED: 3 tests |
| M28 `-relevance` allowed without `q` | RED: 3 tests |
| M29 next cursor drops the mode | RED: walk test and concurrency test |
| M30 fallback count capped at 4 | RED: 2 tests |
| M31 `q` not trimmed | RED: 3 tests |
| M32 suggestions filter with `word_similarity() >= 0.5` (bypasses the index) | RED: `test_search_plans_use_the_gin_indexes[suggestions]` |
| M33 fuzzy uses `%` (whole-name similarity) instead of `<%` | RED: 6 tests |
| M34 search keyset bound inclusive (`<=`) | RED: 6 tests |

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | **Major** | `domain/storefront.py:46-51` (list `q` min length 1); `storefront_query.py:84-86, 101-102`; `test_storefront_scale.py:193-224`; `README.md:27` | A one-letter search puts every name into the trigram fallback (`'s' <% name` scores 0.5 for any word starting with *s*). Each row then gets a `word_similarity` and a sort. **Measured on the 10k seed, two runs:** `q=s` median 420–441 ms, page 2 606–650 ms (max 688 ms). These 12 of the test's 96 samples (12.5 % > 5 %) alone set the p95: 482–526 ms locally, against 65–68 ms for the other shapes. **On the GitHub runner the same test measured 1004 ms, and `main` is red** (run 37783074634) | The slice's NFR-02 "Done when" fails in CI. Every later PR runs this test, and the plan's rule that `main` stays green after every merge is broken. The README's "search p95 56 ms" is not what the test measures | Skip the trigram fallback for terms shorter than 3 characters (full text only, or require 2+ like suggestions), add a test that pins it, re-measure, and correct the README figure. Owner decision on the minimum length: see Q-3 | VS-016 (hotfix, before VS-020) |
| A-02 | **Major** | `test_storefront_search.py:91-103` | SRS §21.5 / database-design §18.1 (name weighted above description) is guarded only by this test. Without `ts_rank` (M09), the name and description hits tie and `id DESC` on random UUIDs decides. The mutation was caught in **3 of 10 runs** | A regression of the A/B weighting, or of using `ts_rank` at all, would pass CI most of the time | Give `described` a fixed top UUID (as `test_a_full_text_hit_outranks…` does at line 138), so a tie would put it first and fail deterministically | VS-016 (tests) |
| A-03 | Minor | `test_search_suggestions.py:59-65` | `far` is `word[:-1] + "x"` and `near` is `word`. Every made-up word ends in a vowel, which sorts before `x`, so ordering by name alone already gives `[near, far]`. M22 (drop the similarity order) survives | The "closest first" contract (`docs/storefront-catalogue.md`, ADR-023 §6) has no effective test | Make the far name sort first alphabetically (e.g. prefix it with `"a "`, or use a lower letter than the last vowel) | VS-016 (tests) |
| A-04 | Minor | `storefront_query.py:96`; no test | No list test has two trigram-only hits of different similarity. M10 (all trigram-only hits score 0) survives | In fuzzy mode, typo results could come back in UUID order unnoticed | Seed two near-miss names (e.g. `Dragonfly` and `Dragoon Shield` for `dragn`) and assert their order | VS-016 (tests) |
| A-05 | Minor | `storefront_query.py:52`; `test_storefront_search.py:72-88` | The tests pin the threshold from below (`plnter` = 0.50) but not from above. M15 (0.3) survives. Probe values: `word_similarity('vase','Base Plate') = 0.400`, `('gear','Year Planner') = 0.400`, `('cat','Coat Hook') = 0.286`. All would match at 0.3 | A loosened threshold would flood results with junk without failing a test | Add a negative case: `vase` must not return "Base Plate" (0.40 < 0.5) | VS-016 (tests) |
| A-06 | Minor | `tests/conftest.py:21-31`; `tests/smoke/test_vs016_smoke.py:1-2` | `VS016_SMOKE` is never imported into `_SMOKE_NODE_IDS`. **Demonstrated:** `pytest -m smoke --collect-only` selects 78 tests, and the only VS-016 one is the existence check. Its docstring claims "`tests/conftest.py` marks each `smoke`" | The VS-016 smoke suite runs nothing of VS-016 | Add `VS016_SMOKE` to the import list and the tuple. Let the existence test also assert that its IDs are in `_SMOKE_NODE_IDS` | VS-016 (tests) |
| A-07 | Minor | `test_storefront_scale.py:157-162` (VS-015 test) | The browse-plan test depends on test order. **Demonstrated:** `pytest test_storefront_search.py test_storefront_scale.py` → `test_browse_plans_use_the_partial_indexes[type_material_colour_price]` FAILS (planner picks `ix_products_browse_category`). With all storefront files ahead of it, `[top_rated]` fails too. Alone, or in the default alphabetical order (scale before search), all 9 pass | Any reorder, `-k` selection, or a new file sorting before `test_storefront_scale.py` that seeds products turns CI red. The plan it falls back to is still an indexed plan, so the assertion is stricter than the requirement | Accept any `ix_products_browse_*` index for the shape, or seed the scale data in an isolated schema/database | VS-015/VS-016 (tests) |
| A-08 | Minor | `test_storefront_scale.py:193-224, 228-254` | The NFR-01/02 p95 checks are wall-clock assertions in the default suite. The repo's own convention (`pyproject.toml:87-90`) keeps machine-sensitive timing under `-m timing`. One of them has already failed CI (A-01) | Hardware noise can turn `main` red; conversely, a fast runner can hide a slow shape | Keep the plan/index assertions and a deterministic work-counting check (e.g. `EXPLAIN (ANALYZE, BUFFERS)` rows/buffers bound per shape) in CI. Move the wall-clock p95 to `-m timing`, run on reference hardware before merge | VS-016 (tests); same pattern in VS-015 |

Also checked, no issue found:

- **Injection.** The term is always a bound parameter (M12 killed). `websearch_to_tsquery` never raises on syntax, and operator-only queries return `[]`.
- **Threshold scope.** The threshold is `set_config(..., true)` (M17 killed).
- **Cursor tampering.** NaN, ±inf and negative relevance keys, a browse cursor with `q`, and a search cursor without `q` all give 422.
- **Cursor reuse.** A cursor reused with a different `q` returns 200 with only matching rows, as ADR-023 documents.
- **Stop words.** `q=the` falls back to trigram and finds "The Thinker Bust".
- **Accents.** `cafe` finds "Café Sign".
- **Float keys.** The relevance key round-trips exactly. The unit test pins a float4-widened value, and the walk test pages 5 sorts with no duplicate or missing row (M34 killed).
- **Adversarial latency on 10k.** A full-text term matching every row (`scale`) takes 83 ms, page 2 at most 203 ms at limit 100. A 200-char alphabet soup takes 316–355 ms. Suggestions on 200 chars take 19–30 ms, and `sc` takes 64 ms.
- **OpenAPI.** All three routes are public, with 422/429 documented.
- **Not VS-016 scope.** The rate limit keys on `request.client.host`, which belongs to VS-020.

## 7. Open questions (SRS ambiguous)

- **Q-1:** In fuzzy mode, websearch operators are ignored. `q=lamp -moon` returns **only "Moon Lamp"**: zero full-text hits, then a trigram match on both words (probe). ADR-023 accepts that an excluded word "can still come back as a near-miss … ranked last". Here, though, it is the whole result and an exact hit on the excluded word. Should a query containing `-`, quotes or `or` skip the trigram fallback? SRS §6.3 says only "fall back when results are thin".
- **Q-2:** The suggestion route gets the VS-010 allowance of 600 requests/hour/IP, and autocomplete fires per keystroke. Lebanese mobile carriers commonly use carrier-grade NAT. Even after VS-020 restores real client IPs, many visitors may share one IP. The SRS sets no number for search. Is 600/h right for autocomplete?
- **Q-3:** What is the minimum `q` length for the list? Suggestions need 2 characters, but the list accepts 1. That single letter causes A-01, and it matches every name with a word starting with that letter (probe: `q=s` → "Self-watering Planter", "Café Sign", "Spiral Vase"). Neither the SRS nor ADR-023 addresses single characters.
- **Q-4:** Typo tolerance covers names only: trigram is on `name` per §21.3, so `paintd` finds nothing while "Hand-painted" is in a description. FR-01 says "typo-tolerant matching is available" without scope. Is name-only intended?

## 8. How the commands were run

- **Commands on the checkout.** I used the repo's `.venv` (Python 3.13.5, ruff 0.16.9). The `.env` file was not read. Tests use their own testcontainers (`postgres:16`, `redis:7-alpine`), with Docker 29.2.1 running. `pytest` runs used `-p no:cacheprovider`, so the checkout stayed clean. The marker suites ran after the full run; the integration suite overlapped with the mutation runs.
- **CI.** I read it with `gh run list --commit 0b1909a` and `gh run view 37783074634 --log-failed`.
- **Scratch copies.** Mutations ran on two `git archive HEAD` copies in the session scratchpad. `PYTHONPATH` pointed at each copy's `src`, which I confirmed with `app.__file__`. The environment came from `.env.example` (as CI does), and each mutation was restored and diffed against HEAD. The scale file was put first in the target list because of A-07. Two runners worked in parallel, each with its own containers.
- **Probes.** Behaviour, latency, per-shape p95 and `word_similarity` values were scratch-only test files in a third copy. They are not part of the repo.

## 9. Resolution (branch `fix/vs-016-audit`)

Owner decisions: **Q-3**, the trigram fallback and suggestions need at least 3 characters. The `srs-reviewer` pass on this branch showed that counting raw characters let `s s`, `(s)` and `s!!` through to the same slow path (456–851 ms on 10k). The rule is therefore implemented as **a word of 3+ letters or digits**, which is what pg_trgm reads. **Q-1**, a query that excludes a word never falls back. Both are recorded in amended ADR-023 decisions 3, 4 and 6. Q-2 and Q-4 were decided on 2026-10-09 (branch `fix/search-rate-limits`). **Q-2**: suggestions allow 3,000 requests/hour/IP (ADR-023 decision 7), and the frontend debounces about 300 ms. **Q-4**: typo tolerance stays on names only for V1 (an accepted limit in ADR-023).

| ID | Fix | Proof |
|---|---|---|
| A-01 | `fuzzy_eligible` and `has_trigram_word` (`domain/storefront.py`): the fallback needs a word of 3+ letters or digits and no exclusion. Exclusion is read from PostgreSQL's own `websearch_to_tsquery` output (`tsquery_negates`), so `lamp - moon` and `(-moon)` count as well. A fuzzy cursor for an ineligible term is a 422. Suggestions need the same word (`suggestion_term_errors`). README figure corrected. The p95 test now also measures `q=sca` at limit 100 (the slowest search still allowed: every seeded name has a word starting with "sca") and `q=s s`. It also asserts that it ran on the seed | `q=s` 17–28 ms (was 420–690 ms); `q=s s` 14–19 ms. With the test's new shape list, p95 is 181 / 174 / 181 ms over three local runs, set by `sca` (page 1 157–196 ms, page 2 213–239 ms). New tests: `test_typo_matching_needs_a_word_of_three_letters` (`s`, `sp`, `s s`, `(s)`, `s!!`, `spi`), suggestion 422s for `ab`, `s s`, `(s)`, `test_an_excluded_word_never_comes_back` (`lamp -moon`, `lamp - moon`, `-moon lamp`, `-moon`), two forged-cursor 422 cases, unit tests for the rule and the parser. Mutations: no length rule (M35), no exclusion rule (M36), no cursor check (M37), raw character count instead of a 3-letter word (M38, 12 tests red): all killed |
| A-02 | `described` gets the top UUID, so a tie lists it first | M09 killed **5/5** |
| A-03 | The far name ends in a digit and has the top UUID, so name order and id order both put it first. A digit precedes every letter in C and `en_US` collations; a space doesn't (`en_US` ignores it at level 1) | M22 killed **5/5** |
| A-04 | `test_trigram_only_hits_are_ordered_by_similarity`: two trigram-only names (0.727 and 0.571, asserted in the test), with the farther one on the top UUID | M10 killed **5/5** |
| A-05 | `test_a_name_below_the_threshold_is_not_a_typo_match`: `vase` must not find "Base Plate" (0.40, asserted to lie between 0.3 and 0.5) | M15 killed **5/5** |
| A-06 | `VS016_SMOKE` wired into `tests/conftest.py`; new `test_the_vs016_smoke_list_is_wired_into_the_marker` | `pytest -m smoke --collect-only`: 118 collected (was 78), including every listed VS-016 test |
| A-07 | The scale module seeds a migrated database of its own (`scale_url` / `scale_engine` / `scale_app`). Plain `ANALYZE` could not fix it: the fixture already ran `VACUUM ANALYZE`, and the planner was correctly reacting to 85 retired categories other tests leave behind (5 live of 90) | The order that failed (`search, suggestions, products, scale`): 133 passed |
| A-08 | **Not moved.** CI runs plain `pytest`, and `addopts` deselects `timing`, so moving the p95 tests under `-m timing` would remove NFR-01/02 from CI entirely. With A-01 fixed, search p95 sits at about 22 % of its budget, including the worst allowed shape | `.github/workflows/ci.yml:39-40`, `pyproject.toml:90` |

M08 (relevance offset 2 → 1) now survives by design. Negated queries never fall back, so a rank-0 full-text hit never shares a page with a trigram match, and the mutation is equivalent (ADR-023 §2).
