# ADR-030: Bring Your Idea submission - optional images under code-constant caps, a pre-parse attempt limit, private storage, expiry stamped at submission, and an admin notification category

**Status:** Accepted
**Date:** 2026-10-17
**Source basis:** Owner decisions of 2026-10-17 on the VS-034 open questions (Q1 to Q11, plus the admin notification); SRS 13.2-13.4, BR-110-BR-115, SEC-11-SEC-16, FR-15; [ADR-021](ADR-021-image-upload-pipeline.md); [ADR-026](ADR-026-captcha-refusal-and-outage.md); SRS §30.3 (retention period, a design-time decision)
**Applies first to:** `POST /api/v1/custom-requests` (VS-034). VS-035 builds the admin pipeline on these tables.

## Context

Bring Your Idea is the only public route that accepts files. ADR-021 fixed the image pipeline for an administrator-only route, where the caller is authenticated before the body is read. A guest route has no such boundary: whatever it accepts, it accepts from anyone. The SRS asks for "size and count caps" without numbers, leaves the retention period open (§30.3), and says nothing about who learns that a lead arrived.

## Decision

1. **Images are optional, 0 to 5 per request, each at most 10 MB and 40 MP.** These are the ADR-021 bounds, kept as code constants (security bounds, not BR-133 settings). An idea with no picture is still a lead; requiring one would suppress the casual enquiries SRS 13.2 exists to capture.
2. **Order of checks:**
   1. a per-IP attempt limit of 20 per hour, and a declared `Content-Length` of at most 5 × 10 MB + 64 KiB, both in the route class **before the multipart body is parsed** (a missing `Content-Length` is refused too);
   2. the text fields, the file count and each file's size;
   3. the captcha (ADR-026);
   4. 5 per hour per IP and 5 per hour per email (the contact form's numbers);
   5. per file, the ADR-021 pipeline: scan the raw bytes, sniff, decode, re-encode;
   6. store every file, then insert the request, its attachment rows and the notifications, then commit.

   The attempt limit is lower than the contact form's 60 because one attempt may carry 50 MB to spool. A file refused after the captcha has spent its quota, which is what the quota is for.
3. **Private storage, generated keys.** Files go under `UPLOADS_PRIVATE_DIR` as `custom-requests/<uuid4>.<jpg|png|webp>`, a shape a CHECK constraint enforces. No route serves them; VS-035 adds the admin-only `X-Accel-Redirect` download. The client's filename is kept only for display: base name, no control characters, at most 255 characters, `image` if empty.
4. **All or nothing for the lead.** Every file is screened before any is stored. If storage or the insert fails before commit, the files already written are deleted at once. A failed commit leaves orphans that `reap_orphan_files`, now also run over `custom-requests/` in private storage, removes after its 24-hour grace period (ADR-021 point 3).
5. **Retention: `custom_request_attachment_retention`, 90 days by default, editable from 1 to 365 days.** This settles SRS §30.3 for V1. `expires_at` is stamped when the request is submitted, so a changed setting applies to new attachments only. `purge_expired_attachments` runs daily. Per batch it locks rows with `expires_at <= now` (`SKIP LOCKED`), deletes the files, then deletes the rows. The lead itself is kept for the funnel.
6. **Administrators are notified in-app.** In the same transaction, every active, live administrator gets one notification with `payload.event = "custom_request.submitted"`, the request id and project title, and no name, email or phone. Each insert runs in its own savepoint. A failed one rolls back alone and is logged (`custom_request_notification_failed`, ids and a count only), and the request still commits, as FR-15 requires ("Notification failure does not remove the submitted request"). This needs a seventh `notification_type` category, `custom_request`, because none of database-design §12.3's six (account, order, payment, refund, offer, download) describes a lead.
7. **Schema choices.**
   - No `user_id`: the route ignores auth cookies, so nothing would write it. The same rule VS-033 applied to `contact_messages`.
   - `scan_status` is an enum with the single value `clean`: scanning is synchronous, so no other verdict is ever stored.
   - The VS-035 pipeline columns (quote, outcome, notes, the `*_at` timestamps, the queue index) are created now, because VS-035 has no migration.
   - No `version` column: VS-035 transitions serialise on a row lock plus a state check.
8. **An empty multipart value counts as absent.** FastAPI reads an empty form part as missing, so an empty `captcha_token` is `422 VALIDATION_ERROR` here rather than ADR-026's `400`. It is still refused without calling Cloudflare. A blank file part, as a browser sends for an empty file input, is `422` as well: the client must omit `attachments` when there are none.

## Consequences

+ An anonymous flood stops at 20 parsed bodies per IP per hour, and only captcha-verified requests reach ClamAV or Pillow.
+ No attachment is ever public, and no row ever points at an unscanned or missing file.
+ A lead and its announcements commit together; administrators never hear about a request that rolled back, and a broken notification never costs a lead.
− A ClamAV outage blocks only submissions that carry images. A Cloudflare outage blocks every submission (ADR-026).
− nginx `client_max_body_size` (VS-020) must allow about 51 MB on this one location.
− The project title is free text the visitor typed, so the notification shows whatever they wrote there.
− Shortening the retention setting does not shorten attachments already stored.

## Alternatives rejected

- **Required images.** They would suppress the leads the channel exists to capture.
- **The contact form's 60/hour attempt limit.** At 50 MB per attempt it would let one IP push 3 GB an hour through multipart parsing.
- **Computing expiry at purge time from `created_at`.** That would let a shortened setting delete images an administrator expected to keep, and the table design already has `expires_at NOT NULL`.
- **Reusing an existing notification category** such as `account`. It would mislabel the event, and the category is what clients filter on.
- **Treating the empty-token case specially to keep `400`.** It would need a non-standard form parser for a case no correct client produces.
