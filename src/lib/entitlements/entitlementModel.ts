// #ARCHITECTURE-ENTITLEMENT-ADAPTER
//
// Frontend-normalized presentation model ONLY — NOT a claim about the
// real /me/entitlements response field names, which are still
// NEEDS BACKEND CONFIRMATION (FVS-020-IMPLEMENTATION-PLAN.md §1). A
// future API adapter maps whatever the backend actually returns onto
// this shape.
//
// #SECURITY — deliberately excludes any storage path, private
// object-storage URL, internal storage key, download endpoint/href, or
// revoked/status field. Revoked entitlements are never returned by the
// list endpoint at all (VS-017's own "revoked hidden" rule) — there is
// no revoked variant to model, not a hidden one. Download delivery is
// FVS-021's own concern, never this model's.
export interface EntitlementModel {
  id: string;
  productDisplayName: string;
  thumbnailSrc?: string;
  currentVersionLabel?: string;
}
