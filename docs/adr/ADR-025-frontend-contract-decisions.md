# ADR-025: Admin order lines list their legal next actions; customers can check STL ownership; Turnstile captcha on five public forms

**Status:** Accepted
**Date:** 2026-10-14
**Source basis:** Owner decisions of 2026-10-14 on the open questions in [`../frontend-handoff/BACKEND-RESPONSE.md`](../frontend-handoff/BACKEND-RESPONSE.md) section 7 (items 1, 2 and 7); SRS SEC-12, §2.2; ADR-019 decision 5; ADR-022; ADR-024 decisions 4, 5, 8
**Amends:** [ADR-022](ADR-022-storefront-commerce-capabilities.md), whose consequence "making the flag per-user would need an authenticated variant of the endpoint, which V1 doesn't have" no longer holds: decision 2 adds a separate authenticated check. ADR-022's decisions stand; the public product endpoint stays anonymous.

## Context

The frontend team's unlock request asked three things the specification left open:

- **Admin order lines.** The line state machine depends on product type, fulfillment method, payment method, payment state (BR-148) and, for cancels, on which `cancel_reason` values are allowed from which state (ADR-024). Without help from the API, the admin screens would have to re-encode that table and keep it in step with the server.
- **STL ownership.** `GET /api/v1/products/{slug}` is anonymous, so it cannot say "you already own this". A customer only found out when the cart refused the add with `409 PRODUCT_ALREADY_OWNED`.
- **Captcha.** SEC-12 requires captcha on all public unauthenticated forms, but the plan applied it only to contact and Bring Your Idea, and no vendor was named. Registration, resend verification and the password-reset request are public forms too, protected today only by per-IP rate limits and uniform responses.

## Decision

1. **`AdminOrderDetail` returns `available_actions` on every line** (VS-029; the STL edge from VS-023b). It lists the transitions `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` would accept for that line at the moment of the read:

   ```json
   "available_actions": [
     { "target_status": "ready_to_ship", "cancel_reasons": [] },
     { "target_status": "cancelled", "cancel_reasons": ["refused", "other"] }
   ]
   ```

   - `cancel_reasons` is empty when the transition takes no reason, and otherwise lists the reasons allowed from the line's current state; one of them is then required.
   - It is computed from the same pure transition table the endpoint enforces, including the BR-148 payment gate, the rule that a cash order reaches `delivered` / `picked_up` only through the cash handover, and the $0 `shipped → cancelled` edge. A line with nothing legal has `[]`.
   - It is a read-time hint. The transition endpoint stays the authority: a concurrent change still answers `409 INVALID_STATE_TRANSITION`, and the client re-reads the order.
   - Customer responses do not carry it; customers keep the `can_cancel` and `payment_due` flags.

2. **A signed-in customer can check STL ownership for one product** (VS-023): `GET /api/v1/me/stl-ownership?product_id=<uuid>` answers `200 {"product_id": "<uuid>", "owned": <bool>}`.
   - `owned` is true when the caller has a paid, unrefunded STL line for that product (`awaiting_delivery` or `delivered`, not fully refunded): the definition of ownership in ADR-019.
   - A product that is unknown, hidden or physical answers `owned: false`, so the endpoint reveals nothing about which products exist.
   - Any signed-in user may call it; a verified email is not required, because it changes nothing.
   - Missing or malformed `product_id`: `422 VALIDATION_ERROR`. Anonymous: `401 AUTH_REQUIRED`.
   - It is a hint for the product page. The cart (`409 PRODUCT_ALREADY_OWNED`) and checkout, backed by the ownership index, still refuse a second purchase. That includes an STL held by the customer's own unpaid order, for which this endpoint answers `owned: false`.

3. **Captcha is Cloudflare Turnstile on five public forms** (VS-033): `POST /api/v1/auth/register`, `POST /api/v1/auth/resend-verification`, `POST /api/v1/auth/password-reset/request`, `POST /api/v1/contact-messages` and `POST /api/v1/custom-requests`.
   - VS-033 builds the `CaptchaPort` (SRS §18), a Turnstile adapter and a fake adapter. The fake adapter is refused outside the `test` and `development` environments, by allowlist, as the malware scanner's is.
   - Each of the five requests gains a required `captcha_token` field (a multipart field on Bring Your Idea). The secret is `TURNSTILE_SECRET`; the site key is public and lives in the frontend's configuration.
   - On the three authentication routes the captcha is verified before any account is looked up. A refused captcha gives the same answer whatever the email address, and the enumeration floor (SEC-06) still applies, so the captcha cannot become an account-existence oracle.
   - VS-033 adds one stable error code for a refused or missing token to api-endpoints.md §5.2. Its name and status are chosen in VS-033.
   - Not covered: login (it has its own per-email throttle and lockout), email verification and password-reset confirmation (each needs a single-use token from the user's mailbox).

## Consequences

+ The admin screens render only the buttons the server would accept, with the right reason picker, and never duplicate the state machine.
+ The product page can say "you already own this" before the customer tries to buy it again.
+ Every public form that can send email or store data is protected by the same captcha, as SEC-12 requires.
− `available_actions` must stay in step with the transition table. VS-029 tests that for every line state, every listed action succeeds and every unlisted target is refused.
− Captcha on registration is a breaking change to `RegisterRequest`, `ResendVerificationRequest` and `PasswordResetRequest`: request schemas forbid unknown fields, so the frontend cannot send `captcha_token` before VS-033 ships, and old clients fail after it. The frontend widget and VS-033 must be released together.
− The three authentication flows now depend on Cloudflare being reachable. VS-033 decides how a Turnstile outage is answered; failing open would defeat the control.
− Every existing registration, resend and reset test must send a token accepted by the fake adapter.

## Alternatives rejected

- **An `owned` flag on the public product endpoint** — makes a cacheable, anonymous response depend on the caller.
- **Returning the customer's full list of owned products** — the product page needs one answer, and a list grows with every purchase.
- **Leaving the transition table to the frontend** — two copies of the state machine drift, and the frontend cannot see the payment state BR-148 depends on.
- **Captcha on contact and Bring Your Idea only** — leaves three public forms that send email to arbitrary addresses protected by per-IP limits alone, which carrier-grade NAT weakens.
