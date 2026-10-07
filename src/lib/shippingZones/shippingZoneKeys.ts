// #ARCHITECTURE-CANONICAL-SHIPPING-ZONES
//
// The ONE canonical query-key family for the shipping-zone resource.
// One shared root distinguishes the admin and public reads of the
// same underlying resource without inventing two unrelated caches for
// the same concept (FVS-024-IMPLEMENTATION-PLAN.md §0/T01). Future
// consumers: FVS-024's own admin management, and FVS-026's checkout
// zone-picker (public). Neither list variant takes a page/filter
// argument — pagination/filter contract is unconfirmed for either the
// admin or public endpoint.
export const shippingZoneKeys = {
  root: ["shippingZones"] as const,
  adminList: () => [...shippingZoneKeys.root, "adminList"] as const,
  publicList: () => [...shippingZoneKeys.root, "publicList"] as const,
};
