import { describe, it, expect } from "vitest";
import { toEditableSetting, toEditableSettings, toPatchValue, type RawSettingRead } from "./settingsAdapter";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";

function rawSetting(overrides: Partial<RawSettingRead>): RawSettingRead {
  return {
    key: "accepting_orders",
    type: "boolean",
    value: true,
    description: null,
    unit: null,
    minimum: null,
    maximum: null,
    nullable: false,
    is_public: true,
    updated_at: "2026-01-01T00:00:00Z",
    updated_by: null,
    ...overrides,
  };
}

describe("toEditableSetting", () => {
  it("maps a boolean setting and humanizes the key as a label", () => {
    const result = toEditableSetting(rawSetting({}));
    expect(result).toMatchObject({ key: "accepting_orders", type: "boolean", value: true, label: "Accepting orders" });
  });

  it("maps an integer setting with minimum/maximum", () => {
    const result = toEditableSetting(
      rawSetting({ key: "max_login_attempts", type: "integer", value: 5, minimum: 1, maximum: 10 })
    );
    expect(result).toMatchObject({ type: "number", value: 5, min: 1, max: 10 });
  });

  it("maps a duration setting's unit onto the number variant", () => {
    const result = toEditableSetting(
      rawSetting({ key: "mfa_challenge_ttl", type: "duration", value: 300, unit: "seconds" })
    );
    expect(result).toMatchObject({ type: "number", value: 300, unit: "seconds" });
  });

  it("maps a null, nullable integer to a null value (not 0)", () => {
    const result = toEditableSetting(rawSetting({ key: "foo", type: "integer", value: null, nullable: true }));
    expect(result).toMatchObject({ type: "number", value: null });
  });

  it("maps a string setting", () => {
    const result = toEditableSetting(rawSetting({ key: "whatsapp_number", type: "string", value: "+96170000000" }));
    expect(result).toMatchObject({ type: "string", value: "+96170000000" });
  });

  it("maps a null string setting to an empty string", () => {
    const result = toEditableSetting(rawSetting({ key: "whatsapp_number", type: "string", value: null, nullable: true }));
    expect(result).toMatchObject({ type: "string", value: "" });
  });

  it("maps a money setting", () => {
    const result = toEditableSetting(
      rawSetting({ key: "cash_max_order_total", type: "money", value: { amount_cents: 5000, currency: "USD" } })
    );
    expect(result).toMatchObject({ type: "money", value: { amountCents: 5000, currency: "USD" } });
  });

  it("maps a null money setting to a null value", () => {
    const result = toEditableSetting(rawSetting({ key: "cash_max_order_total", type: "money", value: null, nullable: true }));
    expect(result).toMatchObject({ type: "money", value: null });
  });

  it("maps a json setting as a passthrough value", () => {
    const result = toEditableSetting(rawSetting({ key: "future_flags", type: "json", value: { a: 1 } }));
    expect(result).toMatchObject({ type: "json", value: { a: 1 } });
  });
});

describe("toEditableSettings", () => {
  it("filters out obsolete keys (daily_download_cap, free_shipping_threshold)", () => {
    const result = toEditableSettings({
      items: [
        rawSetting({ key: "accepting_orders" }),
        rawSetting({ key: "daily_download_cap", type: "integer", value: 5 }),
        rawSetting({ key: "free_shipping_threshold", type: "money", value: null, nullable: true }),
      ],
      next_cursor: null,
    });

    expect(result.map((item) => item.key)).toEqual(["accepting_orders"]);
  });
});

describe("toPatchValue", () => {
  it("sends a boolean value verbatim", () => {
    const setting: EditableSetting = { key: "accepting_orders", type: "boolean", label: "Accepting orders", value: true };
    expect(toPatchValue(setting, false)).toBe(false);
  });

  it("converts an empty string to null only when the setting is nullable", () => {
    const setting: EditableSetting = { key: "whatsapp_number", type: "string", label: "WhatsApp number", value: "x", nullable: true };
    expect(toPatchValue(setting, "")).toBeNull();
  });

  it("keeps an empty string as-is when the setting is not nullable", () => {
    const setting: EditableSetting = { key: "name", type: "string", label: "Name", value: "x", nullable: false };
    expect(toPatchValue(setting, "")).toBe("");
  });

  it("converts a money UI value back to the wire shape", () => {
    const setting: EditableSetting = { key: "cash_max_order_total", type: "money", label: "Cash max order total", value: null, nullable: true };
    expect(toPatchValue(setting, { amountCents: 2500, currency: "USD" })).toEqual({ amount_cents: 2500, currency: "USD" });
  });

  it("converts a null money UI value to null", () => {
    const setting: EditableSetting = { key: "cash_max_order_total", type: "money", label: "Cash max order total", value: null, nullable: true };
    expect(toPatchValue(setting, null)).toBeNull();
  });
});
