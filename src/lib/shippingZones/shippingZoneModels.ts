// #ARCHITECTURE-SHIPPING-ZONE-ADAPTER
//
// Frontend-normalized shapes only — never a claim about the real
// admin/public shipping-zone response field names, both unconfirmed
// (FVS-024-IMPLEMENTATION-PLAN.md §0/§1). `currency` is always a
// required, caller-supplied string — never defaulted/hardcoded to
// "USD"/"LBP" anywhere; "Confirm USD settlement/support" remains an
// explicitly open external item (vertical-slice-plan.md §2).
//
// #ARCHITECTURE-EXPLICIT-SHIPPING-ZONE — neither type carries any
// governorate/address field. V1 has no automatic address-to-zone
// mapping; checkout selects a zone explicitly (FVS-026's own concern).
export interface ShippingZoneAdminModel {
  id: string;
  displayName: string;
  rateCents: number;
  currency: string;
  isArchived: boolean;
}

// The public checkout-facing option (FVS-026's future zone-picker).
// Deliberately has NO `isArchived` field — if the public endpoint
// never sends archived zones at all (as VS-019 implies, matching
// FVS-020's own no-revoked-field precedent for entitlements), there is
// nothing for this presentation layer to filter or badge.
export interface ShippingZoneOption {
  id: string;
  displayName: string;
  rateCents: number;
  currency: string;
}
