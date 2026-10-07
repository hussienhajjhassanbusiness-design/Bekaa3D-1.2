// #ARCHITECTURE-ADDRESS-ADAPTER
//
// A frontend-normalized shape only — never a claim about the real
// `/me/addresses` response field names. No individual address field
// (name/phone/street/city/governorate/postalCode/country) is
// confirmed anywhere in the repository (FVS-023-IMPLEMENTATION-PLAN.md
// §0/§1), so none is invented here. `displayLines` is pre-formatted,
// presentation-ready text a future adapter builds once the real
// schema is confirmed — this layer never parses or re-derives
// individual fields from it.
//
// #ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE — this type deliberately
// carries NO shipping-zone/rate field. Address management and
// shipping-zone selection are different concerns (VS-019's own Logic
// line: "explicit active-zone selection"); V1 has no automatic
// governorate-to-zone mapping, so address code must never infer, call,
// or store zone/rate information. Zone selection belongs entirely to
// FVS-026's checkout flow.
export interface AddressModel {
  id: string;
  displayLines: readonly string[];
  isDefault: boolean;
}
