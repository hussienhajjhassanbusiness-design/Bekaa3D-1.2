# ADR-031: Bring Your Idea pipeline - an API-streamed admin download until a server exists, a server-derived outcome, a bounded quote, and a cohort funnel

**Status:** Accepted
**Date:** 2026-10-17
**Source basis:** Owner decisions of 2026-10-17 on the VS-035 plan (Q2 to Q10) and the change of plan that moves VS-020, VS-021, VS-032, VS-047 and VS-048 to a final phase; SRS 13.3, 20.7, BR-111, BR-113-BR-115, FR-15, FR-17; [ADR-030](ADR-030-bring-your-idea-submission.md)
**Amends:** ADR-030 decision 3 ("VS-035 adds the admin-only `X-Accel-Redirect` download")
**Applies first to:** the admin Bring Your Idea routes (VS-035)

## Context

VS-035 depended on VS-020 for nginx, because the plan served private attachments with `X-Accel-Redirect`. The owner moved every slice that needs a server to the end: the project is finished and tested locally first. The administrator still has to see a lead's reference images. The SRS also leaves open how an outcome is recorded, what a quote may contain, and what the funnel counts.

## Decision

1. **The API streams the download.** `GET /api/v1/admin/custom-requests/{id}/attachments/{attachment_id}/download` sits behind the admin boundary (MFA-complete administrators only; others get 401 or 404). It streams the stored bytes in 64 KiB chunks through `StoragePort.open`. `open` checks that the file exists before any header is sent, so a missing file can still answer 404. The file itself is opened only once streaming starts, so a response that is never sent (a failed audit write or commit) leaves no open file handle. The response always sends:
   - `Content-Type`: the stored type (jpeg, png or webp, a database CHECK);
   - `Content-Length`;
   - `Content-Disposition: attachment`;
   - `Cache-Control: no-store`;
   - `X-Content-Type-Options: nosniff`;
   - `Content-Security-Policy: default-src 'none'; sandbox`;
   - `Cross-Origin-Resource-Policy: same-origin`.

   **VS-020 may switch this route to nginx `X-Accel-Redirect`** on an `internal` location over `uploads_private`. The authorisation, expiry check and audit row stay in the API; only the byte transfer moves.
2. **No Range requests.** Images are at most 10 MB, so the route always answers `200` with the whole file. api-endpoints.md §23 is corrected (it listed `206`/`416`). nginx would add Range support for free if VS-020 makes the switch.
3. **A safe download name.** The visitor's display name is kept, but its extension is replaced with the stored type's, so `evil.html` downloads as `evil.jpg`. The header carries an ASCII fallback (`"`, `\` and non-ASCII become `_`) plus an RFC 6266 / RFC 5987 `filename*`.
4. **Expired means gone.** An attachment with `expires_at <= now`, the purge job's own boundary, is `404` before the daily purge runs, and the detail view no longer lists it. Unknown ids, an attachment of a different request, a purged row and a missing file all give the same `404 NOT_FOUND`; a missing file also logs `custom_request_attachment_file_missing`.
5. **The server derives the outcome.**
   - `quoted → in_progress` records `won`: work starts only after an off-platform agreement.
   - `contacted|quoted → lost` records `lost` and stamps `closed_at`, so every finished lead has an end time.
   - `CustomRequestTransition` accepts only `target_status` and `quoted_amount_cents`. `outcome` and `note` are rejected (`extra=forbid`), and notes go through `PATCH`.
   - A same-state transition is `409 INVALID_STATE_TRANSITION`, like any other non-edge.
6. **A bounded quote.**
   - `quoted_amount_cents` is a strict integer from 1 to 100,000,000 ($1M).
   - It is required when moving to `quoted` and refused on any other target (`422`).
   - The currency is always `USD`, set by the server.
   - Zero is refused because a $0 quote is almost always a typo.
   - V1 has no re-quote.
7. **Audit.** The list view, detail view, transitions, notes changes and downloads each write an audit row in the request's transaction. Rows carry ids, statuses, outcome and amount only. A notes change records `has_notes` before and after, never the text: notes may quote the visitor, and audit rows are permanent.
8. **The funnel.** It counts leads by submission date over `[from, to)`:
   - Both bounds need a UTC offset. `to` defaults to now and `from` to 90 days before `to`. The span is at most 366 days.
   - Errors are `422 VALIDATION_ERROR`, like every query parameter in the API. api-endpoints.md §27 is corrected from `400`.
   - A stage counts every lead that ever reached it (`contacted_at`, `quoted_at`, outcome), so a lost quote still counts as quoted.
   - The response returns `submitted`, `contacted`, `quoted`, `won`, `lost`, `open`, `quoted_total_cents`, `won_total_cents` and `currency`.
9. **No migration and no `version` column.** Two administrators racing on one lead serialise on `SELECT … FOR UPDATE` and a recheck of the state (ADR-030 decision 7). The loser gets `409`, or moves on from the winner's state when that is itself a legal edge.

## Consequences

+ VS-035 ships without a server, and the administrator can open every lead's images.
+ The authorisation and audit trail are the same whichever process ends up sending the bytes.
+ Funnel stages can't go backwards when a lead is lost, and money totals stay integer cents in USD.
− Until VS-020, the API process holds an open file and a worker task for each download (at most 10 MB each).
− Without Range, an interrupted download restarts from the beginning.
− A wrong quote can't be corrected in V1: the lead keeps its amount, and the administrator explains it in the notes.

## Alternatives rejected

- **Keep VS-035 waiting for nginx.** It would block the main lead channel's admin side until the very end of the project.
- **`FileResponse` on a filesystem path.** It would tie the route to local storage; `StoragePort.open` also works for the planned S3-compatible store.
- **Client-supplied outcome.** It could contradict the status (a `won` lead in `lost`) and break the funnel.
- **Allowing `0` or re-quoting.** Each adds edit and audit rules the SRS does not ask for.
