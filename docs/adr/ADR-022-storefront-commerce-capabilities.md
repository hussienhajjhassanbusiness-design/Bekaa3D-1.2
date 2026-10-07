# ADR-022: Derive storefront commerce capabilities from product state only

**Status:** Accepted
**Date:** 2026-10-08
**Source basis:** api-endpoints.md §30 (`ProductDetail` derived capabilities); SRS BR-001, BR-003, BR-009, BR-080, INV-07, §5.3, §7.1; vertical-slice-plan VS-015; owner decision of 2026-10-08
**Applies first to:** `GET /api/v1/products/{slug}` (VS-015). The cart (VS-022) and offers must agree with it.

## Context

The `ProductDetail` contract asks for three derived flags: `can_add_to_cart`, `can_offer` and `whatsapp_available`. Without them, every frontend page would have to rebuild the purchase rules from `type`, `purchase_mode` and `is_available`. The SRS doesn't define the flags. Its rules are spread across BR-001/003 (purchase modes), BR-009 (unavailable stops add-to-cart), BR-080 (offers are STL only) and INV-07 (checkout refuses WhatsApp-only, invisible, unavailable or deleted lines).

The detail endpoint is public and anonymous, so it can't know who is asking. One rule is per customer: an STL the customer already owns is refused by the cart (`409 PRODUCT_ALREADY_OWNED`).

## Decision

1. The flags are computed in the Catalog domain (`app.catalog.domain.storefront.capabilities`), from the product alone:
   - `can_add_to_cart` = available AND (STL, or `purchase_mode` is `online_only` or `both`);
   - `can_offer` = STL AND available (pausing an STL also pauses offers);
   - `whatsapp_available` = physical AND `purchase_mode` is `whatsapp_only` or `both`, **whether or not the product is available**, because that conversation happens off the platform.
2. They only ever describe products the storefront would show. Hidden, deleted or inactive-category products are `404`.
3. They are hints for the UI, not authority. The cart, checkout and offer commands re-check everything server-side, including per-customer rules such as STL ownership and the global `accepting_orders` switch.

## Consequences

+ The frontend has one source for "which buttons does this product get", and it is unit-tested against every type, mode and availability combination.
+ VS-022 and the offers slice must apply rules at least as strict as these. If a later rule tightens them (for example the kill switch), the flag may still say `true` while the write is refused. It can never say `false` when the write would succeed.
− A customer who already owns an STL still sees `can_add_to_cart: true` on its page. Making the flag per-user would need an authenticated variant of the endpoint, which V1 doesn't have.
