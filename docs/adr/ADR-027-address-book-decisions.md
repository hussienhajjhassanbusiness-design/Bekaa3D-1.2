# ADR-027: Address book - required landmark notes, E.164 phones in a shared normaliser, a per-user write lock, and a first-address default

**Status:** Accepted
**Date:** 2026-10-15
**Source basis:** Owner decisions of 2026-10-15 on the VS-026 open questions (Q1 to Q8, plus the first-address default); SRS §14.4, BR-071, BR-078, BR-123; FR-03; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) decision 7

## Context

VS-026 builds the address book. Three documents disagreed about `landmark_notes`, nothing said what a Lebanese governorate or phone is, and the deletion and default rules were open (frontend handoff item 10). The address phone also feeds VS-028: it is snapshotted as the order's contact phone, and its keyed hash matches cash-payment blocks and open cash orders across accounts. So two spellings of one number must always normalise identically.

## Decision

1. **Landmark notes are required.** SRS §14.4 calls them "functionally required rather than decorative". That overrides `database-design.md` 5.2 (nullable) and `api-endpoints.md` 29.3 (optional), and both documents are corrected. The column is `NOT NULL` with a non-blank CHECK. `area` and `street` stay optional.
2. **Governorate is one of Lebanon's nine**, stored as a slug (`akkar`, `baalbek_hermel`, `beirut`, `beqaa`, `keserwan_jbeil`, `mount_lebanon`, `nabatieh`, `north`, `south`), with a DB CHECK. City, area and street are free text.
3. **Phones are stored in E.164** (`+961` followed by 7 or 8 digits) and returned that way.
   - `app.core.phone.normalise_lebanese_phone` is the only parser. It lives in the shared kernel so the Ordering domain can use it in VS-028.
   - It accepts the prefixes `+961`, `00961` and `961` (the last only before a national-length number), an optional trunk `0`, and the separators `space ( ) . -`.
   - The national number is either 7 digits starting `1` or `3`–`9`, or 8 digits starting `7` or `8`.
4. **Every address write takes a per-user lock first**: `SELECT … FROM users WHERE id = :uid FOR NO KEY UPDATE`.
   - Without it, two default switches to different targets race. Under READ COMMITTED, the second switch's "clear the old default" misses the row the first switch just made default, so it hits the partial unique index and answers 500.
   - The same lock serialises the 20-address cap count and the first-address default.
   - Address inserts take only `KEY SHARE` on `users`, which this lock does not block. Account anonymisation (VS-045) updates the same row, so it is ordered against address writes for free.
5. **A user's first live address becomes the default automatically**, even if `is_default: false` is sent. Later addresses become default only on request (`PUT …/default`, or `is_default: true` on create or update). Deleting the default leaves none, and nothing is promoted. `PATCH is_default: false` on the default clears it.
6. **At most 20 live addresses per user.** One more is `422 ADDRESS_LIMIT_REACHED`. The list is therefore not paginated.
7. **Deletion is soft and never refused in V1.** No checkout exists yet, and orders snapshot the address. VS-028's checkout locks the chosen address `FOR SHARE` and refuses a deleted one with `422 INVALID_FULFILLMENT`, so the `409` listed in `api-endpoints.md` 9.2 is not needed. A deleted row is never default (CHECK).
8. **No audit row, notification or rate limit** on customer address writes. Customer self-service on their own data is outside the audited set (project brief: payment, authentication, STL delivery, upload and administrator actions), and the cap bounds storage.

## Consequences

+ VS-028 gets a validated, normalised phone for free. The cash-limit hash cannot be dodged by spelling one number two ways.
+ "At most one default" holds under concurrency, proven by a race test with the lock removed (14 of 15 runs fail).
− The 8-digit range is broad (`7x`, `8x`): an unassigned prefix such as `72` is accepted. The courier and the administrator call before dispatch, which catches a wrong number. Narrowing it later only refuses input.
− A user who sends `is_default: false` for their first address still gets a default.
− `addresses.user_id` is `ON DELETE RESTRICT`, stricter than the CASCADE `database-design.md` allows. Only never-verified accounts are purged, and they cannot write addresses.

## Alternatives rejected

- **The `phonenumbers` library.** It is a new dependency for one country, its metadata changes between releases, and a release that changed a normalisation would orphan every stored cash-block hash.
- **A transaction-scoped advisory lock keyed on the user id.** It would work, but it would be a second lock the VS-045 anonymisation has to know about. The `users` row is the natural owner.
- **Promoting another address when the default is deleted.** It would silently choose a delivery address the customer did not pick.
