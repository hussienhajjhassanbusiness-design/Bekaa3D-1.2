# ADR-020: Use an optimistic `version` column for administrator edits

**Status:** Accepted
**Date:** 2026-10-07
**Source basis:** FR-04 (concurrent access), vertical-slice-plan VS-013; owner decision of 2026-10-07 on version scope
**Applies first to:** `products` (VS-013)

## Context

FR-04 requires that "conflicting administrator edits must not silently overwrite protected business fields; an optimistic version or equivalent conflict check should return a conflict response". Earlier admin slices (VS-007, VS-009, VS-010) serialise concurrent writes with `SELECT … FOR UPDATE`. A row lock makes the second write *wait*, but it doesn't make it *fail*. Two administrators who opened the same product form both succeed, and the later save silently replaces the earlier one, which is the overwrite FR-04 forbids.

The conflict has to be detected against what the administrator *read*, not against what the row holds when the write arrives. So the client has to send back a token naming the state it edited.

## Decision

1. **Each versioned table gets `version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)`**. Every read returns it.
2. **A mutation must carry the version the administrator last read.** `PATCH` takes it in the JSON body (`version`). `DELETE` takes it as a required query parameter (`?version=N`), because a DELETE has no conventional body. A missing or invalid version is `422 VALIDATION_ERROR`.
3. **The write is `UPDATE … WHERE id = :id AND version = :version`, and it sets `version = version + 1`.** PostgreSQL re-checks the predicate after any concurrent writer commits. So of two writers holding the same version, exactly one updates a row, and the other updates none.
4. **No row updated means `409 VERSION_CONFLICT` with nothing written**, audit row included. The problem body carries `current_version` as an RFC 9457 extension member, so the client can re-read and retry. The application also compares versions on its first read, so a plainly stale request fails before any work is done.
5. **Scope of the version (owner decision):**
   - Only administrator-editable fields bump it. Server-maintained aggregates (`average_rating`, `review_count`, `wishlist_count`), written by later slices, do **not** bump it. Otherwise a review arriving mid-edit would fail the administrator's save with a conflict they can do nothing about.
   - A PATCH that submits the stored values is a no-op. It writes nothing and does not bump the version, but it is still audited with equal before/after, as in the VS-007 convention.
6. **Audit snapshots include `version` and exclude the aggregates.** That keeps them consistent with point 5: the snapshot describes exactly the state the version guards.

## Consequences

+ A stale edit can never overwrite a newer one. Proven by `tests/concurrency/test_product_version_race.py`, which fails if the `version` predicate is removed.
+ No lock is held while an administrator has a form open, and no lock-wait timeouts.
+ `VERSION_CONFLICT` is one stable code that other admin resources can adopt when they need it.
- Clients must round-trip `version`. A client that ignores it gets 422, not a silent overwrite.
- Aggregate writers must not bump `version` (point 5). VS-036 and VS-038 must follow this when they maintain `review_count` and `wishlist_count`.
- A no-op PATCH is audited against a version it doesn't re-check at write time. Accepted, because nothing is written.

## Alternatives rejected

- **`If-Match` / `ETag` with `412 Precondition Failed`.** Standard HTTP, but the slice plan fixes `409 VERSION_CONFLICT`, and a 412 would be the project's only one.
- **Row lock only (`FOR UPDATE`).** Serialises the writes but still lets the later one overwrite, so it doesn't meet FR-04.
- **`updated_at` as the version token.** Microsecond timestamps can collide across a clock adjustment, and a no-op leaves them unchanged by design.
- **SQLAlchemy `version_id_col`.** It does the same thing implicitly. An explicit conditional `UPDATE` keeps the rule visible in one repository method and maps directly onto the 409.
