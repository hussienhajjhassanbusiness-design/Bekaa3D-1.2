# FVS-021 — Customer STL Download Experience — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: CRITICAL — digital delivery security/performance.

**Goal:** From the library (FVS-020), a customer downloads their current STL file via a real browser navigation (never fetch/Blob) and views download history. This batch builds `DownloadButton` (the architecturally critical native-anchor component), the normalized history model, `DownloadHistoryTable`, and `DownloadNotice` — then correctly defers the real download-href adapter, the history API integration, and the unresolved cap/revoked error-surfacing question.

**Architecture:** `DownloadButton` is a real `<a href>`, nothing else — no JS download handler ever. `downloadHistoryModel.ts` is a normalized shape with a presentation-ready `dateLabel`, never a raw timestamp this layer formats itself. `DownloadHistoryTable` renders both a desktop `<table>` and a mobile stacked list simultaneously, CSS-only visibility switching (no JS viewport detection), avoiding duplicate screen-reader content via `display:none`'s own accessibility-tree exclusion. `DownloadNotice` is a safe, adapter-fed presentational seam — never a pre-flight-fetch trigger.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-018 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-021 entry.

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-018), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-021, existing §17 gaps), `FVS-020/019/018/007-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/account/`, `src/components/feedback/`, `src/lib/api/`, `src/app/account/`. Searched for `downloads`/`download history`/`Range`/`X-Accel`/`Content-Disposition`/`daily cap`/`reset`/`entitlement`/`authorized download`/`blob`/`createObjectURL` and any OpenAPI source.

**Confirmed by repository evidence:**
- `GET /api/v1/me/downloads` is literal/confirmed (VS-018's own "Endpoint / entrypoint" line) — the entitlement-file download endpoint itself is explicitly **not** given a path anywhere ("Entitlement-file download endpoint" is prose only), matching the task's own framing.
- The native-anchor architecture is a confirmed, non-negotiable requirement: VS-018's Logic line states the backend "return[s] nginx `X-Accel-Redirect`" and "support[s] HTTP Range via nginx" — a `fetch`→`Blob`→`createObjectURL` path would silently break both. `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-021 entry repeats this explicitly as the reason for a plain anchor.
- Daily cap is a confirmed server-side check (VS-018's Logic line: "daily cap") — exact status/code/reset-time field are not given.
- **The critical error-UX contract question (how a cap/revoked failure surfaces through a native anchor navigation) remains genuinely unresolved** — neither document specifies a redirect-with-error mechanism, a separate eligibility endpoint, or an RFC-problem-response-in-browser approach. Per the task's own explicit instruction, **no preflight fetch was added** to "solve" this; it is recorded as the single highest-priority backend question (§4, Q29/Q30) rather than guessed.

**Confirmed account-nav state:** `ACCOUNT_NAV_ITEMS` still contains only `Profile` — no `Downloads`/`Library` link was added, consistent with the registry's own "never a dead placeholder" rule and FVS-020's own decision.

**What is genuinely unconfirmed:** the exact download-endpoint path and required ids; the history response envelope/pagination/field names; the exact cap-exceeded status/code/reset-time format; whether a pre-download eligibility signal exists at all; the exact revoked/stale-access status (403 vs. 404); and — critically — the mechanism by which any of these errors would ever reach the frontend given a plain anchor navigation.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **History** | Endpoint path | **CONFIRMED** (literal) |
| **History** | Response envelope, pagination, fields | **NEEDS BACKEND CONFIRMATION** |
| **Download** | Endpoint path | **NEEDS BACKEND CONFIRMATION** — explicitly prose-only |
| **Download** | Native-anchor (not fetch/Blob) architecture | **CONFIRMED, non-negotiable** |
| **Download** | X-Accel-Redirect/Range support | **CONFIRMED** (server-side) |
| **Cap** | Daily cap exists as a server rule | **CONFIRMED**; exact status/code/reset-time **NEEDS BACKEND CONFIRMATION** |
| **Error surface** | How a native-anchor failure reaches usable frontend UX | **UNRESOLVED — highest-priority open question, not guessed** |
| **Revoked** | Exact stale-access status (403 vs 404) | **NEEDS BACKEND CONFIRMATION** |
| **Account nav** | `Downloads` link | **CORRECTLY WITHHELD** — no real route exists yet |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Authorized `DownloadButton` anchor | **CAN IMPLEMENT NOW** |
| T02 | Normalized download-history presentation model | **CAN IMPLEMENT NOW** |
| T03 | `DownloadHistoryTable` responsive presentation | **CAN IMPLEMENT NOW** |
| T04 | Cap/revoked notice presentation seams | **CAN IMPLEMENT NOW** |
| T05 | Real history query/API adapter | **BLOCKED ON RESPONSE CONTRACT** |
| T06 | Real download-href adapter + error integration | **BLOCKED ON DOWNLOAD CONTRACT + the unresolved error-surface question** |
| T07 | `/account/downloads` route + FVS-020 library integration + nav | **BLOCKED** until T05/T06 unblock |
| T08 | Integration/E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T03, T04. T05–T07 blocked; T08/T09 blocked.

---

## 4. Backend Questions For Tomorrow

**History:** 1. Exact response envelope. 2. Is history paginated? 3. Exact item id. 4. Product name field. 5. Filename field. 6. Version field. 7. Downloaded-at timestamp. 8. Ordering. 9. Is a failed/cap-rejected attempt included in history, or successful downloads only?

**Download:** 10. Exact authorized download endpoint. 11. Required path/query ids. 12. HTTP method. 13. Same-origin? 14. Authentication mechanism/cookies. 15. CSRF required for a GET-style download? 16. Content-Disposition behavior. 17. Exact Range support behavior. 18. Does browser resume work through the same endpoint? 19. Any signed URL/redirect involved? 20. Confirm the frontend must never see an internal X-Accel/storage path (strongly implied already, asking for explicit confirmation).

**Cap:** 21. Exact daily cap. 22. Is the cap a configurable VS-007 public setting or a private business rule? 23. Exact cap-exceeded HTTP status. 24. Exact RFC 9457 code. 25. Reset-time field. 26. Reset-time timestamp/format. 27. Timezone/window semantics. 28. Is remaining quota/count exposed before download? **29. Is there a safe pre-download eligibility endpoint?** **30. If no preflight exists, how should the frontend show friendly cap UX while preserving anchor navigation?** (Q29/Q30 are the single highest-priority pair in this entire plan.)

**Revoked/stale:** 31. Revoked-entitlement response: 403 or 404? 32. Exact RFC code. 33. How should native-browser navigation return the user to application UI on failure? 34. Is there a redirect-with-error mechanism? 35. Should stale library data be invalidated after a failed download?

**Security:** 36. Are authorized download URLs stable or short-lived? 37. Can the href be bookmarked? 38. Must the href never include storage information (strongly implied, confirming explicitly)? 39. Any CSP considerations?

**Testing:** 40. Disposable entitled-customer setup. 41. Download fixture. 42. Daily-cap fixture/reset procedure. 43. Revoked-after-page-load fixture. 44. Range/resume acceptance procedure. 45. History verification after a download.

---

## 5. Task Detail (Safe Batch)

### FVS021-T01 — `DownloadButton`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/DownloadButton.tsx` (+test).
**Design:** `{authorizedHref, accessibleLabel}` — a real `<a href>`, nothing else. No `download` attribute (backend `Content-Disposition` stays authoritative over the saved filename, never a client guess). No `target="_blank"` (same-tab native navigation preferred, no product requirement says otherwise). `accessibleLabel` is required with no inferred fallback — "Download" alone is explicitly disallowed; the caller must supply full file/product context (e.g. "Download Dragon STL").
**Marker:** `#ARCHITECTURE-NATIVE-STL-DOWNLOAD`, `#SECURITY-AUTHORIZED-DOWNLOAD-HREF`.
**Tests:** 9 (real anchor, exact href preserved, exact accessible label used, not a button, no `download` attribute, no `target`, no network, no `URL.createObjectURL` call, no storage).

### FVS021-T02 — Normalized Download-History Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/entitlements/downloadHistoryModel.ts` (+test).
**Design:** `DownloadHistoryItem {id, productDisplayName, dateLabel}` — `dateLabel` is a presentation-ready string, not a raw `Date`/timestamp this model formats itself; no governing document defines timezone/display conversion rules, so none are invented. No backend field names are claimed.
**Marker:** `#ARCHITECTURE-DOWNLOAD-HISTORY-ADAPTER`.
**Tests:** 2 (accepts the normalized fields; has no raw timestamp field at the type level).

### FVS021-T03 — `DownloadHistoryTable`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/DownloadHistoryTable.tsx` (+test).
**Design:** loading/error/retry/empty/populated states, matching `EntitlementList`'s own established pattern. Desktop/tablet (`tablet:table`, i.e. ≥768px) renders a real `<table>`/`<thead>`/`<tbody>`/`<th scope="col">` with exactly two columns (product, downloaded-date) — the source itself says mobile needs no horizontal scroll since there are only a few columns. Mobile (`tablet:hidden`) renders the same data as a semantic stacked list. Both representations exist in the DOM at all times; CSS (`hidden`/`tablet:table` on the table, `tablet:hidden` on the list) decides which one is actually visible, and the hidden one's `display:none` already excludes it from the accessibility tree — so there is no duplicate screen-reader announcement despite the dual markup, with no JS viewport detection anywhere. No pagination control is fabricated, since history's pagination status is unconfirmed.
**Tests:** 11 (loading, error, retry, empty message, real table with `scope="col"` headers, every item's name/date rendered, CSS-hidden table classes present, CSS-hidden mobile-list classes present, no fabricated pagination controls, no network, no storage).

### FVS021-T04 — `DownloadNotice`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/DownloadNotice.tsx` (+test).
**Design:** `kind: "cap" | "revoked" | "generic"` with an optional `resetTimeLabel` (shown verbatim if supplied — never calculated client-side, since Retry-After/reset-time semantics are unconfirmed). No backend status/RFC code is mapped to a `kind` anywhere in this component — that mapping is a future adapter's job once the error-surface question (§0/§4 Q29/Q30) is answered. Critically, **this component is never wired to a preflight fetch** — it only renders from state a parent already has; the native-anchor architecture remains authoritative regardless of how these notices eventually get populated.
**Tests:** 5 (general cap guidance without a reset time, exact reset-time text included verbatim when supplied, revoked message, generic message, no network).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API call, no guessed history/download DTOs, no href construction from storage metadata, no preflight fetch, no cap/revoked status-code mapping, no `/account/downloads` route, no account-nav `Downloads` link, no real download E2E, until T05/T06/T07 unblock.
- **Documentation note for future contributors (per the task's own explicit instruction):** downloads intentionally use a plain anchor. Do **not** refactor this into a `fetch`→`Blob` flow — doing so would silently break HTTP Range, resume, large-file streaming, and the backend's own `X-Accel-Redirect` delivery path. This is recorded here and in `DownloadButton.tsx`'s own `#ARCHITECTURE-NATIVE-STL-DOWNLOAD` comment, both searchable.
