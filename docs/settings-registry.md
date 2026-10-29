# Setting registry

Typed, administrator-editable business parameters (F-114, BR-133). The point of
the table is that operational changes never require a deployment — an
administrator edits a value through the admin API and it takes effect on the
next request.

- **Values** live in the `settings` table.
- **Rules** — which keys exist, their type, limits, unit, and whether they are
  public — live in `src/app/platform/domain/settings_registry.py`.

That split is deliberate. A value is operational, so it changes at runtime. A
rule is logic, so changing it is a code change with a test and a review. A key
that is not in the registry cannot be read, written, or created through the API,
whatever rows happen to be in the table.

## Where the numbers came from

The SRS specifies **none** of these values. It says each is "configurable" and
stops there; the NFR document says so explicitly for one of them (*"Unverified
accounts — Configurable purge period — Exact duration is not fixed by the
SRS"*), and three more are listed as **Awaiting Client** in SRS §30.2.

The defaults below are therefore **V1 product decisions**, taken deliberately
rather than inferred from the specification. Changing one is a migration if you
want the new value to apply to a fresh deployment, or a `PATCH` if you want it
to apply now.

## The sixteen settings

| Key | Type | Unit | Default | Range | Public |
|---|---|---|---|---|:-:|
| `accepting_orders` | boolean | — | `false` | — | ✅ |
| `offer_response_window` | duration | seconds | `172800` (48 h) | 3 600 – 604 800 | ❌ |
| `offer_checkout_window` | duration | seconds | `86400` (24 h) | 3 600 – 604 800 | ❌ |
| `offer_rejection_cooldown` | duration | seconds | `604800` (7 d) | 0 – 2 592 000 | ❌ |
| `minimum_offer_percentage` | integer | percent | `70` | 0 – 100 | ❌ |
| `checkout_hold_period` | duration | seconds | `1800` (30 min) | 300 – 7 200 | ❌ — also bounds payment retry (from `placed_at`); the release deadline runs from the later of placement and the latest attempt (VS-024) |
| `unverified_account_purge_period` | duration | seconds | `2592000` (30 d) | 604 800 – 7 776 000 | ❌ |
| `cash_payment_enabled` | boolean | — | `true` | — | ✅ |
| `cash_max_open_orders` | integer | unpaid, uncancelled cash orders, plus those the customer cancelled in the last 24 h (ADR-038 d23), / customer or contact phone | `1` | 1 – 10 | ❌ |
| `cash_max_order_total` | money | cents (USD) | `10000` (100 USD) | 1 – 1 000 000 cents | ✅ |
| `pickup_address` | string | — | `null` | ≤ 500 chars | ✅ |
| `pickup_hours` | string | — | `null` | ≤ 200 chars | ✅ |
| `whatsapp_number` | string | — | `null` | E.164, ≤ 15 digits | ✅ |
| `security_token_retention_period` | duration | seconds | `604800` (7 d) | 86 400 – 7 776 000 | ❌ |
| `session_retention_period` | duration | seconds | `2592000` (30 d) | 86 400 – 7 776 000 | ❌ |
| `custom_request_attachment_retention` | duration | seconds | `7776000` (90 d) | 86 400 – 31 536 000 | ❌ |

### Notes on individual settings

**`accepting_orders` defaults to `false`.** A freshly deployed system has no
catalogue and no verified payment provider (it had no shipping zones either,
before ADR-024 removed them). Defaulting to
open would mean the one window in which checkout is unconfigured is also the one
in which customers can reach it. An administrator opens the shop deliberately.

**`offer_rejection_cooldown` allows `0`.** Zero means "no cooldown", which is a
legitimate operating choice rather than a degenerate value — so unlike the other
durations its minimum is not bounded away from zero.

**`unverified_account_purge_period` defaults to 30 days** because that is
exactly what the purge job did from a source-code constant before VS-007.
Deployment therefore changes no behaviour; it only moves the control from code
into the database.

**The two retention periods (VS-046)** drive `purge_expired_security_records`.
Tokens are deleted 7 days past `expires_at`, which keeps the `410` link-expired
answer for a week. Sessions are deleted 30 days after they end (the earlier of
expiry and revocation). See [`security-retention.md`](security-retention.md).

**`custom_request_attachment_retention` defaults to 90 days (VS-034)**, which
settles the design-time decision in SRS §30.3 for V1. It is stamped onto each
attachment's `expires_at` at submission, so a change affects new uploads only;
`purge_expired_attachments` deletes the file and the row once that moment passes.
See [`custom-requests.md`](custom-requests.md) and ADR-030.

**`free_shipping_threshold` was deleted on 2026-10-20 (VS-028 PR A, migration
`fcd589e89e59`).** ADR-024 removed BR-076: the courier prices and collects
delivery, so there is no threshold. It left the table, the registry and the public
allowlist together; its admin route now answers `404`. A downgrade restores it as
JSON `null`.

**The cash settings (VS-028, ADR-024 d7, BR-145)** were seeded by the same
migration. `cash_payment_enabled` switches cash off without touching online orders
or existing cash orders. The two limits bound how much printing a fake or refused
cash order can waste (SRS §9.8); the total is checked after checkout recomputes it,
and is at least 1 cent because a cash order's total must be above zero (it is never
null). The maximum total is public because checkout must tell the customer why cash
is unavailable; the open-order limit is private, like other abuse limits. Checkout
starts reading them in VS-028 PR B.

**`pickup_address`, `pickup_hours` and `whatsapp_number` default to JSON
`null`** because the real values are awaited from the client (SRS §30.2). They
are served publicly, so a plausible-looking placeholder address would be worse
than a visibly absent one — the frontend hides an element whose value is null.

## JSON null is not SQL NULL

`settings.value` is `JSONB NOT NULL`, yet three settings default to null (`free_shipping_threshold`, the fourth, was deleted by VS-028). Those
are two different nulls:

- **SQL NULL** means "no value in this column". Forbidden here.
- **JSON `null`** is a value — a present JSON document whose content happens to
  be `null`. That is what an unconfigured setting stores.

The model sets `JSONB(none_as_null=False)` so Python `None` is written as JSON
`null` rather than SQL NULL.

## Public settings

`GET /api/v1/settings/public` is unauthenticated and returns exactly six keys (VS-028,
2026-10-20; before it, `free_shipping_threshold` was the fifth key and the cash keys were
absent):

```
accepting_orders, cash_payment_enabled, cash_max_order_total, pickup_address, pickup_hours, whatsapp_number
```

Two independent things stop an internal setting leaking, and **both** would have
to be removed for one to escape:

1. Only the allowlisted keys are queried at all (`WHERE key IN (...)`), so a
   private setting never leaves the database.
2. `PublicSettingsRead` is a fixed Pydantic schema with a field per allowlisted
   key — not a dictionary — so a value with no matching field has nowhere to go.

Adding a row to the `settings` table therefore cannot make it public. Making a
setting public is an edit to the registry *and* to the response schema, in a
reviewed change.

VS-028 changed the allowlist this way (ADR-024): `free_shipping_threshold` left it, and
`cash_payment_enabled` and `cash_max_order_total` joined it, through the registry and
`PublicSettingsRead` together, as described above.

Of today's sixteen seeded keys, the ten not in the six-key list are internal. `daily_download_cap` was deleted by VS-023b (ADR-019: no files are downloaded).
Its migration, `7a1c3e9b5d24`, re-seeds it on downgrade.

## Validation

Enforced by `validate_value()` before anything is written, and again when an
internal consumer reads a value:

- **boolean** — exactly `true`/`false`. `1` and `0` are rejected.
- **integer / duration** — whole numbers only. Decimals, numeric strings, and
  `true`/`false` are rejected. In Python `True` *is* an `int`, so the check
  compares the exact type; a naive `isinstance` would read `true` as 1.
- **money** — exactly `{"amount_cents": <int>, "currency": "USD"}`. V1 currency
  is fixed by ADR-008.
- **string** — trimmed, non-empty, within its length limit. `whatsapp_number`
  must additionally be canonical E.164: a leading `+`, a non-zero first digit,
  up to 15 digits, no separators.
- **null** — accepted only where the table above shows a `null` default.

A value that fails returns `422 SETTING_INVALID` listing every reason it failed,
not just the first.

## Endpoints

| Method + path | Auth | Notes |
|---|---|---|
| `GET /api/v1/admin/settings` | Admin + MFA | Cursor page, ordered by key; `limit` (default 20, max 100), `prefix`, `type` |
| `GET /api/v1/admin/settings/{key}` | Admin + MFA | `404` for an unknown key |
| `PATCH /api/v1/admin/settings/{key}` | Admin + MFA + CSRF | `422 SETTING_INVALID` on a bad value; audited |
| `GET /api/v1/settings/public` | Public | The six allowlisted keys (VS-028); rate limited |

Keys cannot be created through the API. A new setting arrives as a registry
entry plus a migration that seeds its row.

`PATCH` requires the CSRF header because it is an unsafe cookie-authenticated
method (SEC-03), even though the endpoint table in `api-endpoints.md` does not
spell it out.

## Concurrency and audit

Every update runs as:

```
SELECT ... FOR UPDATE  ->  validate  ->  capture current value
                       ->  update if changed  ->  append audit  ->  commit
```

The row lock gives **last-commit** semantics with an honest audit trail. Two
administrators racing produce `10 → 20` then `20 → 30`, because the second one
waits for the lock and then re-reads. Without it both would record `10 → …` and
the log would describe a history that never happened.

Every accepted `PATCH` is audited as `setting.updated` on entity type `Setting`,
carrying the actor, before and after values, request id and hashed IP. **A
no-op is still audited** — FR-18 requires both of two concurrent attempts to be
recorded, and under last-commit the second frequently *is* a no-op — but it does
not touch `updated_at` or `updated_by`, because nothing changed. A *rejected*
attempt is not an audit event; it is an input error.

The setting write and its audit row are in one transaction. A committed change
with no audit row is exactly the gap BR-132 exists to close.

## Reading settings from other contexts

Other bounded contexts must not query the `settings` table. Use
`SettingsReader` (`app.platform.application.services.settings_reader`), which
takes the caller's session so a read happens in the caller's transaction —
FR-18 requires checkout to recheck `accepting_orders` *inside* its transaction,
which is only meaningful on the same snapshot.

`SettingsReader` validates on read and raises if a setting is missing or its
stored value is invalid. There is deliberately no fallback: a consumer that
silently substituted a constant would reintroduce the hardcoded business
parameter BR-133 forbids, and would do it invisibly.
