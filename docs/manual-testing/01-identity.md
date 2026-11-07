# 01 — Identity

Accounts, sessions, MFA, profile, address book, account deletion and admin user management.
Requirements: FR-02, FR-03, FR-18; BR-120 to BR-126, BR-132; SEC-03 to SEC-08, SEC-10.

**Who can call** (used in every file):

| Label | Meaning |
| --- | --- |
| Anonymous | no session needed |
| Customer | signed in; an unverified email is fine |
| Verified | signed in with a verified email (`403 EMAIL_VERIFICATION_REQUIRED` otherwise) |
| Admin | administrator with MFA complete; a customer gets `404 NOT_FOUND`, anonymous `401 AUTH_REQUIRED`, an admin without MFA `401 MFA_REQUIRED` |

Code locations: routers in `src/app/identity/api/`, use cases in
`src/app/identity/application/commands/`, rules in `src/app/identity/domain/`, auth dependencies
in `src/app/identity/api/dependencies.py`.

Session cookies (set by login and MFA verify): `access_token` (httpOnly, 15 minutes),
`refresh_token` (httpOnly, 30 days, path `/api/v1/auth`), `csrf_token` (readable, 30 days).

---

## Registration and verification

### `POST /api/v1/auth/register`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 5 per hour per IP; captcha |

Creates an account and queues a verification email. **Enumeration-safe**: the answer is the
same `202` for a new address, an unverified one and a verified one (BR-120, FR-02). For an
existing unverified account it re-sends the email at most once per 2 minutes. The response time
is padded so the branches cannot be told apart.

Request:

```json
{"email": "new.customer@example.com", "password": "correct-horse-1", "captcha_token": "XXXX.DUMMY.TOKEN.XXXX"}
```

Response `202`:

```json
{"message": "If eligible, a verification email has been sent."}
```

| Status | Code | When |
| --- | --- | --- |
| 400 | `CAPTCHA_INVALID` | captcha token empty or refused (the fake accepts only `XXXX.DUMMY.TOKEN.XXXX`) |
| 422 | `VALIDATION_ERROR` | bad email, password under 8 or over 256 characters, unknown field |
| 429 | `RATE_LIMITED` | over 5 per hour from this IP |
| 503 | `SERVICE_UNAVAILABLE` | captcha provider unreachable (`Retry-After: 30`) |

Code: `identity/api/auth.py` (`register`), `application/commands/register_user.py`,
`application/services/verification.py` (24 h token, 2 min resend cooldown).

| ID | Test | Expected |
| --- | --- | --- |
| ID-01 | Register a new address with the dummy captcha token | `202`; one `verification_email` row in `email_outbox` for that address |
| ID-02 | Register the same address again at once | `202`, same body; no second outbox row (2 min cooldown) |
| ID-03 | Register `seed-customer@example.com` (already verified) | `202`, same body; no outbox row |
| ID-04 | Register with `captcha_token: "wrong"` | `400 CAPTCHA_INVALID`; no user created |
| ID-05 | Password `short1` (7 characters) | `422 VALIDATION_ERROR`, `loc` `["body","password"]` |
| ID-06 | Add an extra field `"role": "admin"` | `422 VALIDATION_ERROR` (unknown fields forbidden) |

### `POST /api/v1/auth/verify-email`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 20 per hour per IP |

Redeems the token from the verification link and marks the email verified (BR-121). Single use;
the token is valid 24 hours.

Request: `{"token": "<from email_outbox, after #token=>"}`. Response: `204`, no body.

| Status | Code | When |
| --- | --- | --- |
| 400 | `INVALID_TOKEN` | unknown token, already used, or the account is already verified |
| 410 | `RESOURCE_EXPIRED` | token older than 24 hours |
| 422 | `VALIDATION_ERROR` | token over 128 characters, missing |

Code: `identity/api/auth.py` (`verify_email`), `application/commands/verify_email.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-07 | Stop the worker, read the token for ID-01's address (overview §4.6), verify | `204`; `GET /me` after login shows `email_verified: true` |
| ID-08 | Send the same token again | `400 INVALID_TOKEN` |
| ID-09 | Send `{"token": "abc"}` | `400 INVALID_TOKEN` |

### `POST /api/v1/auth/resend-verification`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 5 per hour per IP; captcha |

Re-sends the verification email to an unverified account, at most once per 2 minutes.
Enumeration-safe: always the same `202`.

Request: `{"email": "...", "captcha_token": "XXXX.DUMMY.TOKEN.XXXX"}`. Response `202`:
`{"message": "If eligible, a verification email has been sent."}`.

Errors: `400 CAPTCHA_INVALID`, `422 VALIDATION_ERROR`, `429 RATE_LIMITED`, `503 SERVICE_UNAVAILABLE`.

Code: `identity/api/auth.py` (`resend_verification`), `application/commands/resend_verification.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-10 | Register an address, wait 2 minutes, resend | `202`; a second `verification_email` row; the older token still works until used |
| ID-11 | Resend for an unknown address | `202`, same body; no outbox row |

---

## Sessions

### `POST /api/v1/auth/login`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 20 per hour per IP, plus the per-(email, IP) throttle |

Checks email and password. A customer (verified or not) gets a session: `200 SessionRead` and
the three cookies. An administrator with MFA enabled gets **`202`** with a challenge and **no
cookies**; they finish at `/auth/mfa/verify`. Failures are audited as `user.login_failed`
(ADR-050).

Throttle (SEC-05): attempts 1-3 free, 4-7 delayed 1/2/4/8 s, 8-9 delayed 8 s, the 10th refused for
15 minutes. A successful login resets the counter.

Request: `{"email": "seed-customer@example.com", "password": "..."}`.

Response `200` (customer):

```json
{
  "user_id": "6a1f…",
  "email": "seed-customer@example.com",
  "role": "customer",
  "email_verified": true,
  "session_expires_at": "2026-12-07T10:00:00Z"
}
```

Response `202` (administrator): `{"challenge_id": "k3…", "expires_in_seconds": 300}`.

| Status | Code | When |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS` | unknown email or wrong password (one answer for both) |
| 403 | `ACCOUNT_DISABLED` | right password, but the account is deactivated |
| 422 | `VALIDATION_ERROR` | bad email format, missing field |
| 429 | `RATE_LIMITED` | 20 per hour per IP exceeded, or the 10th attempt for this (email, IP): `Retry-After: 900` |

Code: `identity/api/auth.py` (`login`), `application/commands/login.py`,
`application/services/login_throttle.py`, `application/services/admin_mfa_gate.py`,
`api/failed_login.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-12 | Log in as the seed customer | `200`; cookies `access_token`, `refresh_token`, `csrf_token` in DevTools; no token in the body |
| ID-13 | Log in as the seed admin | `202` with `challenge_id`; no cookies set |
| ID-14 | Wrong password for the customer | `401 INVALID_CREDENTIALS`; an audit row `user.login_failed` |
| ID-15 | Unknown email | `401 INVALID_CREDENTIALS`, the same body as ID-14 |
| ID-16 | Wrong password 4 times in a row | the 4th answer takes about 1 s longer; then reset the throttle (overview §4.7) |
| ID-17 | Deactivate a test customer (ID-60), log in with the right password | `403 ACCOUNT_DISABLED` |

### `POST /api/v1/auth/logout`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Customer or admin (access **or** refresh cookie) | yes | no | none |

Ends the session named by the access token, or by the refresh token once the access token has
expired, and clears the cookies. An access token already issued keeps working for the rest of its
15 minutes (ADR-006, accepted).

Request: no body. Response: `204`, cookies cleared.

| Status | Code | When |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | neither cookie is present or valid |
| 403 | `CSRF_INVALID` | missing or wrong `X-CSRF-Token` |

Code: `identity/api/auth.py` (`logout`, `_session_to_end`), `application/commands/logout.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-18 | Log out with the CSRF header | `204`; the cookies disappear from DevTools; `POST /auth/refresh` now answers `401` |
| ID-19 | Log out without the CSRF header (clear Authorize first) | `403 CSRF_INVALID`; still logged in |

### `POST /api/v1/auth/refresh`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Holder of a refresh cookie | yes (against the refresh token's session) | no | 60 per hour per IP |

Rotates the refresh token and issues a new access token. The session's end date does not move.
Replaying an older refresh token kills the whole session (reuse detection). MFA-complete state is
kept across rotation.

Request: no body. Response: `204`, new cookies.

| Status | Code | When |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | no refresh cookie, invalid, expired, revoked, or a replayed older token |
| 403 | `CSRF_INVALID` | missing or wrong `X-CSRF-Token` |
| 429 | `RATE_LIMITED` | over 60 per hour |

Code: `identity/api/auth.py` (`refresh`), `application/commands/refresh_session.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-20 | Logged in, call refresh with CSRF | `204`; `access_token` cookie value changes; `csrf_token` stays the same |
| ID-21 | Copy the `refresh_token` value, refresh once, then put the old value back in DevTools and refresh again | `401 AUTH_REQUIRED`; the session is revoked (the next refresh with the new token also fails) |

---

## Password reset

### `POST /api/v1/auth/password-reset/request`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous | no | no | 5 per hour per IP; captcha |

Queues a `password_reset_email` with a 1-hour token. Always `202` with the same body: for an
unknown address, a deactivated one, or one inside its 2-minute cooldown nothing is written.
Unverified accounts are eligible.

Request: `{"email": "...", "captcha_token": "XXXX.DUMMY.TOKEN.XXXX"}`. Response `202`:
`{"message": "If an account exists for that address, a reset email has been sent."}`.

Errors: `400 CAPTCHA_INVALID`, `422 VALIDATION_ERROR`, `429 RATE_LIMITED`, `503 SERVICE_UNAVAILABLE`.

Code: `identity/api/auth.py` (`request_password_reset`),
`application/commands/request_password_reset.py`, `application/services/password_reset.py`.

### `POST /api/v1/auth/password-reset/confirm`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous (the token is the credential) | no | no | 20 per hour per IP |

Replaces the password, burns the token and every other unused reset token of the account,
**revokes every session** and advances the account's auth epoch, so every access token and
pending MFA challenge dies at once (SEC-08, ADR-018). MFA enrolment is not touched.

Request: `{"token": "<from reset_url>", "new_password": "another-good-pass-2"}`. Response `204`,
cookies cleared.

| Status | Code | When |
| --- | --- | --- |
| 400 | `INVALID_TOKEN` | unknown, already used, or the account can no longer sign in |
| 410 | `RESOURCE_EXPIRED` | token older than 1 hour |
| 422 | `VALIDATION_ERROR` | `new_password` under 8 or over 256 characters |

Code: `identity/api/auth.py` (`confirm_password_reset`),
`application/commands/confirm_password_reset.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-22 | Window A: log in as a test customer. Window B: request a reset, read `reset_url` (worker stopped), confirm with a new password | `204`; in window A the next authenticated call answers `401 AUTH_REQUIRED` at once (not after 15 min) |
| ID-23 | Log in with the old password | `401 INVALID_CREDENTIALS`; the new one works |
| ID-24 | Confirm again with the same token | `400 INVALID_TOKEN` |
| ID-25 | Request a reset for an unknown address | `202`, same body; no outbox row |
| ID-26 | Request twice within 2 minutes for the same account | both `202`; only one `password_reset_email` row |

---

## Administrator MFA

### `POST /api/v1/auth/mfa/verify`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous with a login challenge | no (no session exists yet) | no | 10 per 15 minutes per IP |

Completes an administrator's login with a TOTP code or a recovery code (exactly one) and sets
the cookies; the session is MFA-complete. The challenge is single-use, lives 5 minutes, and is
consumed **before** the code is checked: a wrong code means logging in again. A TOTP code works
once per 30-second step.

Request: `{"challenge_id": "k3…", "code": "123456"}` or
`{"challenge_id": "k3…", "recovery_code": "abcd-efgh"}`. Response `204`, cookies set.

| Status | Code | When |
| --- | --- | --- |
| 401 | `MFA_INVALID` | wrong code, used code, replayed TOTP step, unknown or spent recovery code (one answer for all) |
| 403 | `ACCOUNT_DISABLED` | the account was deactivated after the password was accepted |
| 410 | `RESOURCE_EXPIRED` | challenge unknown, already used, expired, or minted before a password reset |
| 422 | `VALIDATION_ERROR` | both `code` and `recovery_code`, or neither; code shorter than 6 |
| 429 | `RATE_LIMITED` | over 10 per 15 minutes |

Code: `identity/api/mfa.py` (`verify_mfa`), `application/commands/mfa_verify.py`,
`application/commands/mfa_complete_login.py`, `application/services/mfa_session.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-27 | ID-13's challenge + the current TOTP code | `204`; cookies set; `GET /api/v1/admin/settings` answers `200` |
| ID-28 | Log in again, verify with a wrong code | `401 MFA_INVALID`; verifying again with the right code on the same challenge gives `410 RESOURCE_EXPIRED` |
| ID-29 | Log in twice inside one 30 s step, verify both with the same code | the first `204`, the second `401 MFA_INVALID` |
| ID-30 | Send both `code` and `recovery_code` | `422 VALIDATION_ERROR` |
| ID-31 | Verify with a recovery code from the credentials file | `204`; that code is now spent (do this last, or rotate the seed credentials afterwards) |

### `POST /api/v1/auth/mfa/setup`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Administrator session, MFA **not** required | yes | no | 5 per hour per IP |

Starts TOTP enrolment for an administrator who has none, after re-checking the password. Returns
the secret once. MFA is not on until `/setup/confirm`.

Request: `{"current_password": "..."}`. Response `200`:
`{"secret": "JBSW…", "otpauth_uri": "otpauth://totp/…", "issuer": "Bekaa3D", "account_name": "admin@…"}`.

| Status | Code | When |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS` | wrong `current_password` |
| 401 | `AUTH_REQUIRED` | no session |
| 403 | `CSRF_INVALID` | no CSRF header |
| 404 | `NOT_FOUND` | caller is a customer |
| 409 | `INVALID_STATE_TRANSITION` | MFA already enabled |
| 429 | `RATE_LIMITED` | over 5 per hour |

Code: `identity/api/mfa.py` (`setup_mfa`), `application/commands/mfa_setup.py`.

### `POST /api/v1/auth/mfa/setup/confirm`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Administrator session, MFA not required | yes | no | 10 per hour per IP |

Proves the authenticator works, enables MFA, returns ten recovery codes once, and makes the
current session MFA-complete.

Request: `{"code": "123456"}`. Response `200`:
`{"recovery_codes": ["…", "…"], "generated_at": "2026-11-07T10:00:00Z"}`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | customer, or no enrolment started |
| 409 | `INVALID_STATE_TRANSITION` | MFA already enabled |
| 422 | `MFA_INVALID` | the code does not match the enrolled secret |

Code: `identity/api/mfa.py` (`confirm_mfa_setup`), `application/commands/mfa_confirm_setup.py`.

There is no API to create an administrator, so enrolment can only be tested with an
administrator created in the database. With the seed admin you can test the refusals:

| ID | Test | Expected |
| --- | --- | --- |
| ID-32 | Seed admin (MFA on): `POST /auth/mfa/setup` with the right password | `409 INVALID_STATE_TRANSITION` |
| ID-33 | Seed customer: `POST /auth/mfa/setup` | `404 NOT_FOUND` |
| ID-34 | Seed admin: `POST /auth/mfa/setup/confirm` with any code | `409 INVALID_STATE_TRANSITION` |

### `POST /api/v1/auth/mfa/recovery-codes/regenerate`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Admin (MFA complete) | yes | no | 5 per hour per IP |

Voids every unused recovery code and returns a new set once, after re-checking the password.

Request: `{"current_password": "..."}`. Response `200` `MfaRecoveryCodesRead` (as above).

| Status | Code | When |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS` | wrong password |
| 401 | `MFA_REQUIRED` | admin session without MFA |
| 404 | `NOT_FOUND` | customer |

Code: `identity/api/mfa.py` (`regenerate_recovery_codes`),
`application/commands/mfa_regenerate_recovery_codes.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-35 | As the MFA-complete admin, regenerate with the right password | `200`, ten new codes; an old code now gives `401 MFA_INVALID` at verify. **Save the new codes in the credentials file.** |
| ID-36 | Regenerate with a wrong password | `401 INVALID_CREDENTIALS`; old codes still valid |

---

## Profile and account deletion

### `GET /api/v1/me`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Customer (or admin) | no | no | none |

Returns the caller's own account. Re-reads the row, so a just-deactivated account gets `401`.

Response `200`:

```json
{
  "id": "6a1f…",
  "email": "seed-customer@example.com",
  "role": "customer",
  "email_verified": true,
  "email_verified_at": "2026-11-01T09:00:00Z",
  "created_at": "2026-11-01T09:00:00Z"
}
```

Errors: `401 AUTH_REQUIRED`. Code: `identity/api/profile.py` (`read_profile`).

| ID | Test | Expected |
| --- | --- | --- |
| ID-37 | Logged in as the customer | `200`, own email, `role: customer` |
| ID-38 | Logged out | `401 AUTH_REQUIRED` |

### `DELETE /api/v1/me`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified | yes | no | 5 per hour per user |

Deletes the account by **anonymising** it, all or nothing (BR-125, BR-126, ADR-047): the email
becomes `deleted+<id>@invalid`, the password unusable, addresses anonymised, live offers
withdrawn and their messages blanked, wishlist erased, contact messages and outbox rows
anonymised, idempotency records deleted, every session revoked. Orders, payments, refunds and
audit rows are kept. The old email can register again.

Request: `{"current_password": "..."}`. Response `204`, cookies cleared.

| Status | Code | When |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS` | wrong password (not a session problem) |
| 401 | `AUTH_REQUIRED` | no session |
| 403 | `CSRF_INVALID` / `EMAIL_VERIFICATION_REQUIRED` | missing CSRF; unverified account |
| 409 | `ACCOUNT_DELETION_BLOCKED` | `reason`: `administrator` (close admins by deactivation), `open_order` (an open order or a non-terminal line), `unsettled_refund` |
| 429 | `RATE_LIMITED` | over 5 per hour |

Code: `identity/api/profile.py` (`delete_my_account`), `application/commands/delete_account.py`,
`domain/anonymisation.py`, `infrastructure/account_erasure.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-39 | Fresh verified test customer with an address and a wishlist item, no orders: delete with the right password | `204`; login with the old email gives `401`; `select email from users where id = '<id>'` shows `deleted+…@invalid` |
| ID-40 | Wrong password | `401 INVALID_CREDENTIALS`; still logged in |
| ID-41 | Customer with an unpaid cash order (`in_progress`) | `409 ACCOUNT_DELETION_BLOCKED`, `reason: open_order` |
| ID-42 | Seed admin | `409`, `reason: administrator` |
| ID-43 | Register again with ID-39's old email | `202`; a new account |

---

## Address book

All under `/api/v1/me/addresses`. Lebanese addresses only (BR-071); at most 20 live addresses
(BR-123). The first address is always the default. Reads need only a session; writes need
verification and CSRF. Another user's address, a deleted one and an unknown id all answer the
same `404`.

Fields: `label` (≤ 50), `recipient_name` (≤ 100), `phone` (Lebanese, stored as E.164 `+961…`),
`governorate` (`akkar`, `baalbek_hermel`, `beirut`, `beqaa`, `keserwan_jbeil`, `mount_lebanon`,
`nabatieh`, `north`, `south`), `city` (≤ 100), `area` (optional, ≤ 100), `street` (optional,
≤ 200), `landmark_notes` (required, ≤ 500, line breaks allowed), `is_default`.

Code: `identity/api/addresses.py`, `api/address_schemas.py`,
`application/commands/address_book.py`, `domain/address.py`, `infrastructure/addresses.py`.

### `GET /api/v1/me/addresses`

Customer; no CSRF. Response `200` `{"items": [AddressRead, …]}`, default first. Errors: `401`.

### `POST /api/v1/me/addresses`

Verified; CSRF.

Request:

```json
{
  "label": "Home",
  "recipient_name": "Rami Haddad",
  "phone": "03 123 456",
  "governorate": "beqaa",
  "city": "Zahle",
  "area": "Hoch el Oumara",
  "street": "Main street",
  "landmark_notes": "Blue gate next to the bakery",
  "is_default": false
}
```

Response `201`:

```json
{
  "id": "1d0e…",
  "label": "Home",
  "recipient_name": "Rami Haddad",
  "phone": "+9613123456",
  "governorate": "beqaa",
  "city": "Zahle",
  "area": "Hoch el Oumara",
  "street": "Main street",
  "landmark_notes": "Blue gate next to the bakery",
  "is_default": true,
  "created_at": "2026-11-07T10:00:00Z",
  "updated_at": "2026-11-07T10:00:00Z"
}
```

| Status | Code | When |
| --- | --- | --- |
| 403 | `CSRF_INVALID` / `EMAIL_VERIFICATION_REQUIRED` | no CSRF; unverified |
| 422 | `VALIDATION_ERROR` | a field too long, blank, unknown governorate, non-Lebanese phone, missing `landmark_notes` |
| 422 | `ADDRESS_LIMIT_REACHED` | already 20 live addresses |

### `GET /api/v1/me/addresses/{address_id}`

Customer. `200 AddressRead`; `404 NOT_FOUND` for unknown, deleted, or another user's.

### `PATCH /api/v1/me/addresses/{address_id}`

Verified; CSRF. Any subset of the fields; `null` clears `area` or `street`; `is_default: true`
makes it the default, `false` clears it. Past orders keep their own snapshot. `200 AddressRead`.
Errors: `403`, `404`, `422` (empty body, invalid field).

### `DELETE /api/v1/me/addresses/{address_id}`

Verified; CSRF. Soft delete; deleting the default leaves no default. `204`. Errors: `403`, `404`.

### `PUT /api/v1/me/addresses/{address_id}/default`

Verified; CSRF; no body. Makes it the default and clears the previous one atomically.
`200 AddressRead`. Errors: `403`, `404`.

| ID | Test | Expected |
| --- | --- | --- |
| ID-44 | As the seed customer, create the address above | `201`; `phone` is `+9613123456`; `is_default: true` (first address) |
| ID-45 | Create a second address with `is_default: false`, then `PUT …/{second}/default` | `200`; the list shows the second first with `is_default: true`, the first `false` |
| ID-46 | `PATCH` the first with `{"street": null}` | `200`, `street: null` |
| ID-47 | `PATCH` with `{}` | `422 VALIDATION_ERROR` |
| ID-48 | Create with `"phone": "+33 1 23 45 67 89"` | `422 VALIDATION_ERROR` on `phone` |
| ID-49 | Create without `landmark_notes` | `422 VALIDATION_ERROR` |
| ID-50 | As a second customer, `GET` the seed customer's address id | `404 NOT_FOUND` |
| ID-51 | Delete the default address | `204`; the list has no default |
| ID-52 | As an unverified account, create an address | `403 EMAIL_VERIFICATION_REQUIRED`; `GET` the list still `200` |
| ID-53 | Create without the CSRF header | `403 CSRF_INVALID` |

---

## Admin user management

Under the admin boundary (`/api/v1/admin/users`). Requirement F-116, SEC-10.
Code: `identity/api/admin_users.py`, `application/commands/set_user_active.py`,
`domain/administrators.py`.

### `GET /api/v1/admin/users`

Admin; no CSRF. Newest first, cursor-paginated. Query: `cursor`, `limit` (1-100, default 20),
`verified`, `active`, `search` (case-insensitive part of the email, ≤ 254). Audited as
`user.list_viewed`.

Response `200`:

```json
{
  "items": [
    {
      "id": "6a1f…",
      "email": "seed-customer@example.com",
      "role": "customer",
      "is_active": true,
      "email_verified_at": "2026-11-01T09:00:00Z",
      "created_at": "2026-11-01T09:00:00Z"
    }
  ],
  "next_cursor": null
}
```

Errors: `401`, `404` (customer), `422` (bad `limit`, tampered `cursor`).

### `GET /api/v1/admin/users/{user_id}`

Admin. `200 AdminUserDetail`; audited as `user.viewed`. `404` for an unknown id.

### `PATCH /api/v1/admin/users/{user_id}`

Admin; CSRF. Body `{"is_active": false}`: the only writable field. Deactivating revokes the
user's sessions and advances their auth epoch, so they are signed out at once. Setting the same
value again changes nothing and writes no audit row.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown id |
| 409 | `INVALID_STATE_TRANSITION` | the account is anonymised or deleted, or it is the last active administrator |
| 422 | `VALIDATION_ERROR` | any other field (`role`, `email`), missing `is_active` |

| ID | Test | Expected |
| --- | --- | --- |
| ID-54 | Admin: `GET /admin/users?search=seed-customer&limit=1` | `200`, one item; an audit row `user.list_viewed` |
| ID-55 | Admin: `GET /admin/users?limit=101` | `422 VALIDATION_ERROR` |
| ID-56 | Admin: `GET /admin/users?cursor=abc` | `422 VALIDATION_ERROR` on `cursor` |
| ID-57 | Customer: `GET /admin/users` | `404 NOT_FOUND`, the same body as `GET /api/v1/admin/nothing-here` |
| ID-58 | Anonymous: `GET /admin/users` | `401 AUTH_REQUIRED` |
| ID-59 | Admin: `PATCH` the seed admin's own id with `{"is_active": false}` (only admin) | `409 INVALID_STATE_TRANSITION` (last active administrator) |
| ID-60 | Window A logged in as a test customer. Admin deactivates them | `200`, `is_active: false`; window A's next call answers `401` |
| ID-61 | Admin reactivates them with `{"is_active": true}` | `200`; they can log in again |
| ID-62 | `PATCH` with `{"is_active": true, "role": "admin"}` | `422 VALIDATION_ERROR` |
| ID-63 | `PATCH` ID-39's anonymised account | `409 INVALID_STATE_TRANSITION` |
