# ADR-021: Scan the raw upload, then re-encode; store before the row commits

**Status:** Accepted
**Date:** 2026-10-08
**Source basis:** SEC-13, SEC-14, SEC-15; FR-04 failure behaviour; SRS §23 (`reap_orphan_files`); vertical-slice-plan VS-014; owner decisions of 2026-10-08
**Applies first to:** product images (VS-014). Bring Your Idea attachments reuse it.

## Context

Every uploaded image must be checked by content rather than by extension (SEC-13), re-encoded so that nothing embedded survives (SEC-14), and malware-scanned (SEC-15).

The VS-014 plan listed the steps as size → type → decode → re-encode → **scan** → store → commit. The same plan also requires "the EICAR test file gives 422 `MALWARE_DETECTED`". Those two can't both hold. EICAR isn't an image, so in that order the type check would reject it first with `UPLOAD_REJECTED`. And a payload hidden inside a valid image would be dropped by re-encoding before the scanner ever saw it. The scanner would only ever examine bytes the platform had just produced itself.

Separately, a filesystem write and a PostgreSQL commit can't be atomic. One of them has to happen first.

## Decision

1. **Pipeline:**
   1. **size** (1 byte to 10 MB);
   2. **scan the raw upload** with ClamAV;
   3. **sniff magic bytes** (JPEG, PNG or WebP only; filename and `Content-Type` are ignored);
   4. **bounded decode** (at most 40 MP);
   5. **re-encode** to a new image built from the pixels alone, keeping the format family;
   6. **lock the product row and check the gallery rules**;
   7. **store** the file under a generated key;
   8. **insert the row and the audit row**;
   9. **commit**.
2. **Fail closed.** If the scanner can't give a verdict (unreachable, timeout, an answer that is neither `OK` nor `FOUND`), the upload is refused with `503 SERVICE_UNAVAILABLE` and nothing is stored.
3. **File first, row second.**
   - A storage failure leaves no row. A product therefore never references a missing image (FR-04).
   - A commit failure leaves a file that no row references. `reap_orphan_files` deletes such files once they are older than a 24-hour grace period.
   - Files of soft-deleted images are kept, because order snapshots may point at them (BR-033).
4. **Generated keys only:** `products/<uuid4>.<jpg|png|webp>`. A CHECK constraint enforces the shape, so a client-supplied name or path can never reach the filesystem.
5. **Limits are code constants**, treated as security bounds like the page size and rate limits, not BR-133 business settings: 10 MB, 20 live images per product, 40 MP, alt text up to 300 characters.

## Consequences

+ EICAR, and malware appended behind a valid image, are both caught. Each is tested.
+ What is stored is always the platform's own encoding; the raw upload never reaches media storage. (Starlette may spool a part over 1 MB to a temporary file while parsing; the upload route refuses a missing or oversized `Content-Length` after the admin boundary and before parsing, so that file is bounded at 10 MB plus framing. nginx `client_max_body_size` (VS-020) bounds it again at the edge.)
+ No upload is accepted while the scanner is down.
- Every upload costs a scan round-trip, even for files the type check would reject anyway. That is acceptable for an administrator-only route.
- ClamAV unavailability blocks image uploads entirely. That is the intended trade-off.
- Orphan files can exist for up to a day plus a job interval. They are publicly addressable only if someone guesses a random UUID.

## Alternatives rejected

- **Scan after re-encoding** (the plan's original order): it can't detect EICAR and only ever scans the platform's own output.
- **Scan both raw and re-encoded:** the second scan adds latency and catches nothing the re-encode didn't already neutralise.
- **Insert the row first, then write the file:** a failed write would leave a row pointing at a missing image, which is exactly what FR-04 forbids.
- **Fail open with a warning:** this contradicts SEC-15 and the slice plan.
