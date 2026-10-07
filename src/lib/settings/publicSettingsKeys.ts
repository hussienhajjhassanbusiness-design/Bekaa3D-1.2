// #ARCHITECTURE-CANONICAL-PUBLIC-SETTINGS
//
// The ONE canonical query-key family for `GET /api/v1/settings/public`
// (confirmed literal — FRONTEND-VERTICAL-SLICE-PLAN.md's own
// FVS-007/FVS-014/FVS-022 endpoint lines). FloatingWhatsAppButton
// (FVS-022), FVS-014's product WhatsApp CTA, and any future FVS-025/026
// free-shipping-threshold consumer MUST share this one cached key
// rather than each inventing its own
// (`whatsappSettingsKey`/`shippingSettingsKey`/`homeSettingsKey`) for
// the same endpoint.
//
// `current()` rather than `list()`/`detail(id)`: unlike entitlements,
// this is a single shared resource — the public-settings endpoint
// returns one snapshot, not a per-id collection — so there is no
// detail variant to add.
export const publicSettingsKeys = {
  root: ["publicSettings"] as const,
  current: () => [...publicSettingsKeys.root, "current"] as const,
};
