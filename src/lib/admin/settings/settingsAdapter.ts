import type { EditableSetting, EditableSettingValue } from "@/components/admin/settings/settingTypes";

// P1-3 (docs/backend-handoff/BACKEND-RESPONSE.md, schema `SettingRead`) —
// the confirmed wire shape. `value`'s real type depends on `type`:
// boolean -> boolean, integer|duration -> number, string -> string,
// money -> RawSettingMoneyValue, json -> an arbitrary object. `value` is
// `null` exactly when `nullable: true` and the setting isn't configured.
export type SettingWireType = "boolean" | "integer" | "string" | "money" | "duration" | "json";

export interface RawSettingMoneyValue {
  amount_cents: number;
  currency: string;
}

export type RawSettingValue = boolean | number | string | RawSettingMoneyValue | Record<string, unknown> | null;

export interface RawSettingRead {
  key: string;
  type: SettingWireType;
  value: RawSettingValue;
  description: string | null;
  unit: string | null;
  minimum: number | null;
  maximum: number | null;
  nullable: boolean;
  is_public: boolean;
  updated_at: string;
  updated_by: string | null;
}

export interface RawSettingPage {
  items: RawSettingRead[];
  next_cursor: string | null;
}

// Backend settings that remain in the list response for historical
// reasons but describe nothing actionable (docs/backend-handoff's own
// notes: ADR-019 removed STL downloads, ADR-024 removed shipping
// charges). AGENTS.md: "do not build special UI" for these — filtering
// them out of the rendered list entirely is the cleanest way to honor
// that without a dead-end row an admin could still try to edit.
const OBSOLETE_KEYS = new Set(["daily_download_cap", "free_shipping_threshold"]);

function humanizeKey(key: string): string {
  const words = key.split("_");
  return words.map((word, index) => (index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word)).join(" ");
}

export function toEditableSetting(raw: RawSettingRead): EditableSetting {
  const base = {
    key: raw.key,
    label: humanizeKey(raw.key),
    description: raw.description ?? undefined,
    nullable: raw.nullable,
  };

  if (raw.type === "boolean") {
    return { ...base, type: "boolean", value: raw.value === true };
  }

  if (raw.type === "integer" || raw.type === "duration") {
    const value = typeof raw.value === "number" ? raw.value : null;
    return {
      ...base,
      type: "number",
      value,
      min: raw.minimum ?? undefined,
      max: raw.maximum ?? undefined,
      unit: raw.unit ?? undefined,
    };
  }

  if (raw.type === "money") {
    const moneyValue =
      raw.value !== null && typeof raw.value === "object" && "amount_cents" in raw.value
        ? { amountCents: (raw.value as RawSettingMoneyValue).amount_cents, currency: (raw.value as RawSettingMoneyValue).currency }
        : null;
    return { ...base, type: "money", value: moneyValue };
  }

  if (raw.type === "json") {
    return { ...base, type: "json", value: raw.value };
  }

  return { ...base, type: "string", value: typeof raw.value === "string" ? raw.value : "" };
}

export function toEditableSettings(page: RawSettingPage): EditableSetting[] {
  return page.items.filter((item) => !OBSOLETE_KEYS.has(item.key)).map(toEditableSetting);
}

// Converts an edited UI value back to the PATCH body's `value` member.
// An empty string only becomes `null` when the backend actually allows
// this key to be unset (`nullable`) — otherwise it is sent verbatim and
// left for the server's own 422 SETTING_INVALID to reject.
export function toPatchValue(setting: EditableSetting, nextValue: EditableSettingValue): RawSettingValue {
  if (setting.type === "string" && nextValue === "" && setting.nullable) {
    return null;
  }
  if (setting.type === "money") {
    const moneyValue = nextValue as { amountCents: number; currency: string } | null;
    return moneyValue === null ? null : { amount_cents: moneyValue.amountCents, currency: moneyValue.currency };
  }
  return nextValue as RawSettingValue;
}
