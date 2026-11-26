---
name: bekaa3d-api-contract
description: Use when writing or reviewing any Bekaa3D frontend code that calls, mocks, types, or documents a backend endpoint — API client functions, TanStack Query hooks, form submission handlers, FVS slice work, or a feature request with no cited backend slice — to prevent inventing endpoints, fields, enums, auth/CSRF behavior, or payment/order/offer logic not present in vertical-slice-plan.md.
---

# Bekaa3D API Contract Discipline

## Overview

`docs/plans/backend/vertical-slice-plan.md` (VS-001–VS-040) is the **only** source of truth for what the Bekaa3D backend does. Not intuition, not "how e-commerce usually works," not what looks reasonable for a REST API. If a request/response shape, endpoint, enum, or behavior isn't in that document (or a confirmed OpenAPI spec / implemented contract), it does not exist yet — and code must not be written as if it does.

**Violating the letter of this rule is violating the spirit of it.** Writing invented code and disclosing the invention afterward is still inventing the contract — it is not a compliant middle ground.

## When to Use

- Before writing any `fetch`/API-client call, query hook, or mutation.
- Before typing a request/response interface for anything backend-related.
- Before implementing a feature request that doesn't cite a specific `VS-xxx` slice.
- When reviewing frontend code (yours or another agent's) that touches the network.

## The Rule

Never silently invent: endpoints, HTTP methods, request fields, response fields, enums, pagination behavior, authentication behavior, authorization behavior, CSRF delivery, payment status, order transitions, offer transitions, download behavior, or upload behavior.

**Authority table — the backend is the sole source for:**

| Domain | Never computed/decided on the frontend |
|---|---|
| Commerce | Prices, discounts, totals, tax, shipping cost, product availability |
| State | Order state, offer state, payment state |
| Access | Permissions, entitlements, STL download permission |

Frontend validation exists to improve UX (fast feedback, fewer round-trips) — it is **never** authoritative. A client-side check that agrees with the server is a courtesy; the server's response is the only real answer.

## What "No Endpoint Exists" Actually Means

If a requested feature has no corresponding `VS-xxx` slice in `docs/plans/backend/vertical-slice-plan.md`:

1. **Say so, first, before writing implementation code.** "This isn't in the backend plan — here's what would need to be confirmed with the backend team before frontend work starts" is a complete and correct response on its own.
2. If a sketch/prototype is genuinely useful to unblock design discussion, it must be **visibly, inline, unmissable** as speculative — not production-shaped code with a disclosure paragraph tacked on at the end (see Real-World Failure below). Mark every invented field/endpoint with an inline `// NEEDS BACKEND CONFIRMATION: <what specifically>` comment at its point of use, not just a prose summary after the code.
3. Log it as an open item in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 (the contract-gap list) rather than letting it live only in a chat response or a code comment that will be forgotten.

## Real-World Failure (baseline, observed)

Asked to build the integration layer for a "Recently Viewed Products" feature — which has no `VS-xxx` slice anywhere in the backend plan — a fresh agent under mild time pressure ("the team wants this sketched out today") did not stop or flag the gap up front. It wrote a complete, confident-looking API contract (`GET/POST /api/v1/recently-viewed`, a custom `X-Guest-Id` guest-identity header scheme it invented whole-cloth, specific field names and casing), fully wired it into TanStack Query hooks and example components, and *only at the very end*, in a closing paragraph, listed six things it had actually guessed. The code itself contained zero inline markers — anyone skimming it, or copy-pasting from it, would see production-ready-looking code with no visible warning.

**The lesson:** disclosure-after-the-fact does not prevent invented contracts from shipping. The code has to look unfinished/flagged *at the point where the invention happens*, or the caveat gets lost the moment the code "looks done."

| Rationalization (verbatim pattern) | Reality |
|---|---|
| "I'll sketch something reasonable and note the assumptions at the end" | By the time code compiles and looks complete, the trailing caveat gets ignored or deleted in the next edit. Mark inline, at the point of invention, or don't write it. |
| "This is just a design exercise / prototype, not real code" | It will be copy-pasted into the real PR the moment it "looks right." Treat every line as if it ships. |
| "The endpoint name is obvious from REST convention" | Bekaa3D's actual paths, casing, and envelope shape are decided by the backend team, not REST convention — confirm, don't infer. |
| "I'll just pick something plausible for the auth/guest-identity mechanism" | Auth/session/CSRF mechanisms are security-relevant and already defined in VS-002/003/005 for authenticated flows — never invent a parallel identity scheme (like a custom guest header) without it being a confirmed backend design. |
| "No backend slice exists, but I can still build the frontend shape" | No backend slice = stop and say so. A frontend shape built on a guessed contract is wasted work the moment the real contract differs, and risks shipping the guess if no one catches it. |

## Red Flags — Stop and Flag Instead

- You're about to write a `fetch`/`apiClient` call to a path that isn't a direct quote from `docs/plans/backend/vertical-slice-plan.md` or a confirmed OpenAPI spec.
- You're inventing a field name because "it's probably called that."
- You're designing an auth/session/identity mechanism (headers, tokens, cookies) that isn't VS-003/VS-005's documented cookie+CSRF model.
- You're about to hide a UI element to "handle" an authorization case instead of relying on the backend to refuse the action (see Authorization below).
- The feature you're building has no `VS-xxx` citation anywhere in your task.

**All of these mean: stop, mark the gap inline (`NEEDS BACKEND CONFIRMATION`), and log it in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 before writing implementation-shaped code.**

## RFC 9457 Error Handling

The backend returns RFC 9457 problem-details responses (VS-001). Parse every non-2xx response into a typed `ApiError` and branch UI treatment by status class — see `bekaa3d-commerce-ux` and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §10 for the per-status-code UI pattern (400/422 inline field errors, 401 silent-refresh, 403/404 existence-hiding, 409 conflict-specific UI, 429 retry guidance, 5xx generic). Never assume a validation-error body shape that hasn't been confirmed — the exact field-level error structure is itself a logged `NEEDS BACKEND CONFIRMATION` item.

## Authentication, CSRF, MFA, Authorization

- Session state is cookie-based and httpOnly (VS-003) — the frontend never reads the session token directly; it derives "am I logged in" from calling `GET /me` and caching the result.
- CSRF uses a double-submit pattern (VS-003) — attach whatever header the backend expects; do not invent a different CSRF mechanism because it seems simpler.
- Admin routes require MFA (VS-005) and non-admin access renders as a real 404, not a "forbidden" page — match this exactly, don't substitute your own access-denied UX.
- **Never expose privileged admin behavior merely by hiding frontend elements.** Hiding a button/menu item/route from a non-admin user is a UX nicety, not an authorization boundary — the underlying API call must independently be refused by the backend. If you're relying on "the button isn't visible so they can't do it," that is not authorization; it's decoration. Every privileged action must fail server-side even if somehow triggered without the UI gate (confirm the backend enforces it — never assume the frontend's hiding is sufficient and skip checking).

## Maintaining the Contract-Gap List

`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 is the living list. When you find a new gap:

```
**Issue:** <short name>
**Backend slice:** <VS-xxx or "none">
**Why frontend needs clarification:** <what breaks without an answer>
**What is currently defined:** <quote/paraphrase from vertical-slice-plan.md>
**What is missing:** <the specific unanswered detail>
**Recommended question:** <one concrete question for the backend team>
```

Append to §17 rather than resolving it by guessing, and rather than leaving it only in a code comment or a chat message that won't be seen again.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing a full, confident API integration for a feature with no `VS-xxx` slice | Say so first; if sketching anyway, mark every invented piece inline, not just in a trailing note. |
| Assuming REST convention for path/casing | Quote the exact path/shape from the backend plan or mark it unconfirmed. |
| Inventing a guest-identity/auth header | Auth/session mechanisms are already defined (VS-003/005) — never parallel-invent one. |
| Hiding an admin button to "protect" an action | Confirm the backend independently refuses it — hiding is not authorization. |
| Treating client-side validation as final | Client validation is UX only; the server's response is authoritative. |
| Letting a caveat live only in chat/PR description | Log it in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 so it isn't lost. |
