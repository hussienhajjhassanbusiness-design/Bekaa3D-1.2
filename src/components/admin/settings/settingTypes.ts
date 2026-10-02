// FVS-007-IMPLEMENTATION-PLAN.md T01 (CAN IMPLEMENT NOW — contract-
// independent).
//
// #ARCHITECTURE-SETTINGS-ADAPTER
//
// This is a frontend-NORMALIZED UI model, not a claim about the backend
// response shape — the real `GET /api/v1/admin/settings` list shape,
// field names, and type-discriminator values are all still
// NEEDS BACKEND CONFIRMATION (FVS-007-IMPLEMENTATION-PLAN.md §1). The
// backend response is intentionally isolated from SettingControl/
// SettingRow by this type: once the real contract lands, a future API
// adapter maps it onto EditableSetting in one place. Future backend-
// contract changes belong in that adapter, not in every component that
// renders a setting.
//
// Only the fields SettingControl/SettingRow actually need exist here —
// no speculative metadata, no generic schema framework.

export type SettingValueType = "boolean" | "number" | "string";

interface EditableSettingBase {
  key: string;
  label: string;
  description?: string;
}

export interface BooleanSetting extends EditableSettingBase {
  type: "boolean";
  value: boolean;
}

export interface NumberSetting extends EditableSettingBase {
  type: "number";
  value: number;
  min?: number;
  max?: number;
  step?: number;
}

export interface StringSetting extends EditableSettingBase {
  type: "string";
  value: string;
}

export type EditableSetting = BooleanSetting | NumberSetting | StringSetting;

export type EditableSettingValue = EditableSetting["value"];
