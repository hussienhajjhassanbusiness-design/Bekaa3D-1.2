# ADR-026: A refused captcha is `400 CAPTCHA_INVALID`, a Turnstile outage fails closed with `503`, and a coarse attempt limit runs before the captcha

**Status:** Accepted
**Date:** 2026-10-15
**Source basis:** Owner decisions of 2026-10-15 on the VS-033 open questions (Q1 to Q5); SRS SEC-12, SEC-06, BR-116; [ADR-025](ADR-025-frontend-contract-decisions.md) decision 3, which left the error code and the outage answer to VS-033

## Context

ADR-025 put Cloudflare Turnstile on five public forms. It left three questions to VS-033: which stable code a refused token gets, how a Turnstile outage is answered (failing open would defeat the control), and how the fake adapter used by tests is kept out of production. One more question came up while building the contact form: once the captcha runs before the rate limits, every bad token costs a call to Cloudflare.

## Decision

1. **`400 CAPTCHA_INVALID`** answers a token that is present but empty, invalid, expired or already used: Turnstile's `missing-input-response`, `invalid-input-response` and `timeout-or-duplicate`. An empty token is refused without calling Cloudflare. A request with no `captcha_token` field at all is `422 VALIDATION_ERROR` like any other missing required field, so the field stays required in OpenAPI.
2. **Fail closed.** Anything that is not a verdict gets `503 SERVICE_UNAVAILABLE` with `Retry-After: 30`, and nothing is stored or sent. That covers a timeout, a network error, a non-2xx answer, a non-JSON answer, `internal-error`, `bad-request`, an unknown error code, and a bad or missing secret (`invalid-input-secret`, `missing-input-secret`). The error codes are logged; the token and the secret never are.
3. **The fake adapter is allowlisted.** `CAPTCHA_PROVIDER` is `turnstile` (the default) or `fake`. `fake` is accepted only when `ENVIRONMENT` is exactly `test` or `development`. `turnstile` needs a non-empty `TURNSTILE_SECRET`. The API checks this at startup, so a misconfigured deployment refuses to boot rather than failing on the first form. The fake accepts only `XXXX.DUMMY.TOKEN.XXXX`, the token Cloudflare's public test site keys issue, so a development frontend works against it unchanged.
4. **Order of checks.**
   - Auth routes: the existing per-IP limit, then the body, then the captcha, then the account lookup. A refusal is therefore the same for every address, and the SEC-06 response-time floor still covers it.
   - Contact form: a coarse per-IP attempt limit (60 per hour), then the body, then the captcha, then the per-IP and per-email limits (5 per hour each), then the insert. A refused captcha spends neither 5-per-hour quota, and a flood of bad tokens stops at 60 Cloudflare calls per IP per hour.
5. **No `remoteip`, `action` or `hostname` checks in V1.** Until VS-020 forwards the visitor's address, `remoteip` would be the proxy's. Tokens are single-use, and Cloudflare already binds the site key to our domains.

## Consequences

+ A Turnstile outage or a bad secret never lets an unverified request through.
+ The frontend gets one code for "reset the widget and try again" (`CAPTCHA_INVALID`) and one for "try again later" (`SERVICE_UNAVAILABLE`).
− When Cloudflare is down, registration, resend verification, the password-reset request and the contact form are all unavailable. Login is not affected.
− A local `.env` written before VS-033 has no `CAPTCHA_PROVIDER`, and the API now refuses to boot with it. Add `CAPTCHA_PROVIDER=fake` (development) or a real `TURNSTILE_SECRET`.
− Siteverify latency (up to the 5 s timeout) adds to the auth routes' response time. It is the same for every address, so it is not an enumeration signal.

## Alternatives rejected

- **Failing open during an outage.** It would turn any Cloudflare incident into an unprotected window, which is exactly what an attacker would wait for.
- **`403` or `422` for a refused token.** `403` is already `CSRF_INVALID` and `ACCOUNT_DISABLED`. `422` means the body breaks the schema, and a refused token is a well-formed string.
- **Mapping a missing field to `CAPTCHA_INVALID` too.** It needs either an optional field in OpenAPI or special handling of validation errors, only to rename an error a correct client never sees.
