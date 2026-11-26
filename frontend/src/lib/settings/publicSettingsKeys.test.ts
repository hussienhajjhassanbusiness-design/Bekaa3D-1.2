import { describe, it, expect } from "vitest";
import { publicSettingsKeys } from "./publicSettingsKeys";

// FVS-022-IMPLEMENTATION-PLAN.md T01 — the ONE canonical public-settings
// query-key family (#ARCHITECTURE-CANONICAL-PUBLIC-SETTINGS).
// `GET /api/v1/settings/public` is a single shared resource (confirmed
// literal — FRONTEND-VERTICAL-SLICE-PLAN.md's own FVS-007/FVS-014/
// FVS-022 endpoint lines), not a per-id collection, so there is no
// `detail(id)` variant — only `root`/`current()`. FVS-022's
// FloatingWhatsAppButton, FVS-014's product WhatsApp CTA, and any
// future FVS-025/026 shipping-threshold consumer MUST share this one
// key rather than each inventing its own
// (`whatsappSettingsKey`/`shippingSettingsKey`/`homeSettingsKey`) for
// the same endpoint.

describe("publicSettingsKeys", () => {
  it("has a stable root key", () => {
    expect(publicSettingsKeys.root).toEqual(["publicSettings"]);
  });

  it("derives the current key from the canonical root", () => {
    expect(publicSettingsKeys.current()).toEqual(["publicSettings", "current"]);
  });

  it("keeps the current key distinguishable from the bare root", () => {
    expect(publicSettingsKeys.current()).not.toEqual(publicSettingsKeys.root);
  });

  it("takes no arguments for current() — there is exactly one shared public-settings resource, not a per-id collection", () => {
    // @ts-expect-error — current() intentionally accepts no arguments
    expect(() => publicSettingsKeys.current("whatsapp")).not.toThrow();
  });
});
