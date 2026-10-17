// #ARCHITECTURE-SETTINGS-ADAPTER
//
// This is a frontend-NORMALIZED UI model. The real `GET /api/v1/admin/
// settings` contract is now confirmed (docs/backend-handoff/
// BACKEND-RESPONSE.md P1-3; schema `SettingRead`): `key`, `type`
// (`SettingType`: boolean|integer|string|money|duration|json), `value`,
// `description`, `unit`, `minimum`, `maximum`, `nullable`, `is_public`,
// `updated_at`, `updated_by`. `src/lib/admin/settings/settingsAdapter.ts`
// maps that wire shape onto this UI model in one place — this file (and
// SettingControl/SettingRow) never sees a backend field name directly.
//
// `integer` and `duration` both map onto the one `number` UI variant
// (duration is just an integer count of seconds server-side) — `unit`
// carries the display suffix ("seconds") so the control stays generic
// rather than needing a fifth near-identical numeric variant. `money`
// and `json` are real, distinct UI variants: money gets a cents-safe
// MoneyInput, json (no V1 setting actually has this type) gets a
// minimal non-editable fallback — never a raw JSON editor.
//
// Only the fields SettingControl/SettingRow actually need exist here —
// no speculative metadata, no generic schema framework.

export type SettingValueType = "boolean" | "number" | "string" | "money" | "json";

interface EditableSettingBase {
  key: string;
  label: string;
  description?: string;
  // Mirrors the backend's own `nullable` flag — read by the settings
  // adapter (src/lib/admin/settings/settingsAdapter.ts) when converting
  // an edited UI value back to a PATCH body: an empty string/null value
  // is only ever sent as `null` for a setting the backend actually
  // allows to be unset. SettingControl itself doesn't branch on this.
  nullable?: boolean;
}

export interface BooleanSetting extends EditableSettingBase {
  type: "boolean";
  value: boolean;
}

export interface NumberSetting extends EditableSettingBase {
  type: "number";
  value: number | null;
  min?: number;
  max?: number;
  step?: number;
  // Backend `unit`, e.g. "seconds" for a duration setting — shown as a
  // label suffix. Undefined for a plain integer with no unit.
  unit?: string;
}

export interface StringSetting extends EditableSettingBase {
  type: "string";
  value: string;
}

export interface MoneySetting extends EditableSettingBase {
  type: "money";
  value: { amountCents: number; currency: string } | null;
}

// No V1 setting has this type (docs/backend-handoff's own notes on
// `SettingType`) — kept only so the UI model stays total over the real
// backend enum rather than silently dropping a future `json` setting.
export interface JsonSetting extends EditableSettingBase {
  type: "json";
  value: unknown;
}

export type EditableSetting = BooleanSetting | NumberSetting | StringSetting | MoneySetting | JsonSetting;

export type EditableSettingValue = EditableSetting["value"];
