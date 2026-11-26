---
name: bekaa3d-frontend-slice-dod
description: Use when about to mark a Bekaa3D FVS slice complete, before committing slice work, before opening a PR for an FVS slice, or when reviewing someone else's FVS implementation, to verify every required completion criterion was actually checked rather than assumed done.
---

# Bekaa3D Frontend Slice Definition of Done

## Overview

`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §19 defines what "done" means for a Bekaa3D FVS slice in prose. This skill is the same checklist in enforceable form, to run at the exact moment a slice is about to be called finished — the moment agents are most tempted to round up.

**REQUIRED BACKGROUND:** `superpowers:verification-before-completion` — that skill covers the general discipline of proving claims with evidence before declaring success; this skill adds the Bekaa3D-specific items that a generic completion check wouldn't know to look for (backend-contract fidelity, IDOR-hiding, money-is-never-client-authoritative, admin-hiding-isn't-authorization). Run both — this doesn't replace it.

**REQUIRED BACKGROUND:** `bekaa3d-api-contract` and `bekaa3d-commerce-ux` — several checklist items below only make sense with those rules in mind.

## When to Use

- Immediately before saying a slice is "done," "ready for review," or "ready to merge."
- Before opening a PR for FVS work.
- When reviewing someone else's FVS PR — walk their diff against this list independently; do not accept their own checklist as verification.

## The Checklist

Every item that applies to the slice must be independently verified, not assumed. "It's a small slice, most of this doesn't apply" is itself a claim — mark items **N/A** explicitly with a one-line reason rather than silently skipping them.

**Traceability**
1. Backend VS dependency identified (cite the exact `VS-xxx`)
2. Frontend FVS identified (cite the exact `FVS-xxx` from `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`)
3. Real API contract used — every endpoint/field traces to `docs/plans/backend/vertical-slice-plan.md`, a confirmed OpenAPI spec, or an implemented backend contract (never invented — see `bekaa3d-api-contract`)
4. Route created and matches the plan's routing table (or a documented, justified deviation)

**Layout**
5. Desktop UI complete
6. Tablet UI checked at 768–1023px
7. Mobile UI checked at ≤767px

**State coverage** — for every state the slice's spec (§5 entry) lists under "UX states":
8. Loading state
9. Empty state
10. Error state
11. Unauthorized state (401 → refresh/redirect, per `bekaa3d-api-contract`)
12. Forbidden state (403/hidden-as-404 per the backend's actual hiding rule — not a guessed one)
13. Not-found state
14. Expired/stale state where relevant (payment windows, offer deadlines, tokens)

**Forms & validation**
15. Client-side form validation implemented (UX only, never authoritative — `bekaa3d-api-contract`)
16. Server validation errors displayed correctly, using the server's message and field mapping

**Accessibility**
17. Accessibility checked against `bekaa3d-brand-ui`'s state/contrast rules
18. Keyboard operation checked (every interactive element reachable and operable without a mouse)
19. Focus state checked (visible focus ring present; modals trap and restore focus)

**Security**
20. Security assumptions checked — no invented auth/CSRF/session mechanism (`bekaa3d-api-contract`)
21. Sensitive information not exposed (no raw storage paths/private URLs, no admin-only fields rendered to non-admins, no privileged action gated by hiding alone)

**Testing**
22. Unit/component tests added
23. Integration tests added where appropriate (mocked API contract behavior, including the slice's documented error cases)
24. End-to-end happy path added/extended where the slice completes a critical journey (`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §16)
25. Important failure path tested (not just the happy path — e.g., price-change conflict, expired window, IDOR-hidden resource)

**Contract fidelity**
26. No invented API behavior anywhere in the diff (re-check against `bekaa3d-api-contract`'s red flags)
27. No unresolved contract assumption silently implemented — anything uncertain is logged in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17, not guessed and shipped

**Build health**
28. Tests passing (actually run, output observed — not assumed from "the code looks right")
29. Build passing
30. Lint/type checks passing

**Process**
31. `superpowers:verification-before-completion` performed (evidence gathered before the "done" claim, not after)
32. Code review performed (see `superpowers:requesting-code-review` / `superpowers:receiving-code-review`)
33. Documentation updated (contract notes, state diagrams shared with backend where the slice's §5 entry calls for it)
34. Slice independently mergeable (doesn't depend on unfinished code in another branch)
35. Main branch remains deployable after merge

## Rationalization Table

| Excuse | Reality |
|---|---|
| "This slice is simple, most states don't apply" | Then mark them N/A with a one-line reason — don't silently skip. A "simple" slice missing the error state is still broken. |
| "I tested it manually, it works" | Manual testing isn't in the checklist for a reason — items 22–25 require actual automated tests, run and observed. |
| "The backend contract is obviously RESTful, I didn't need to check" | This is exactly the failure `bekaa3d-api-contract`'s baseline test caught — "obvious" REST shape ≠ the real contract. |
| "I'll add tests/docs in a follow-up PR" | The slice isn't done until they exist in this PR — a slice split across PRs isn't independently mergeable (item 34). |
| "It's just an admin feature, accessibility matters less" | Items 17–19 apply to admin UI too — `bekaa3d-brand-ui` explicitly includes admin in its component/state rules. |
| "I hid the button so non-admins can't reach it, that's enough" | Item 21 — hiding is not authorization. Confirm the backend independently refuses the action. |
| "Lint/build passed last time I checked" | Re-run now, on the current diff — item 28–30 require current evidence, not a memory of a prior run. |

## Red Flags — Stop Before Claiming Done

- You're about to say "done" without having run tests in this session.
- You're marking an item complete because it's "probably fine."
- A checklist item is skipped with no written reason.
- You're relying on your own self-review instead of `superpowers:requesting-code-review`.
- Any item 26/27 (contract fidelity) is uncertain and you're proceeding anyway instead of logging it in §17.

**All of these mean: stop, gather evidence per `superpowers:verification-before-completion`, and complete the checklist for real before declaring the slice done.**

## Common Mistakes

| Mistake | Fix |
|---|---|
| Treating this as a checkbox to fill from memory | Walk the actual diff/running app against each item — evidence, not recollection. |
| Skipping items silently because "obviously N/A" | Write the one-line reason; a silent skip looks identical to a forgotten item in review. |
| Running this checklist only as the implementer, never as reviewer | A reviewer must independently verify — see `superpowers:receiving-code-review` for how to weigh feedback without deferring blindly. |
| Treating "tests exist" as "tests were run" | Run them now; a stale pass from an earlier commit doesn't count. |
