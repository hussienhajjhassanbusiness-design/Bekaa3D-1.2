"use client";

import { fieldControlClasses } from "@/components/forms/fieldStyles";
import { useId } from "react";
import { TextField } from "@/components/forms/TextField";
import { MoneyInput } from "@/components/forms/MoneyInput";
import type { EditableSetting, EditableSettingValue } from "./settingTypes";

export interface SettingControlProps {
  setting: EditableSetting;
  onChange: (value: EditableSettingValue) => void;
}

// #SHARED-TYPED-SETTING-CONTROL
//
// The one renderer that owns type -> control selection. Adding a new
// backend setting never requires a new hand-built form here — only a new
// EditableSetting variant (settingTypes.ts) and, later, an adapter
// mapping for it. Never a raw JSON editor; no network calls; no server-
// state ownership; no persistence beyond the props/callback it's given.
export function SettingControl({ setting, onChange }: SettingControlProps) {
  const labelId = useId();
  const descriptionId = useId();
  const inputId = useId();
  const hasDescription = Boolean(setting.description);
  const describedBy = hasDescription ? descriptionId : undefined;

  if (setting.type === "boolean") {
    return (
      <div>
        <span id={labelId} className="font-label text-label-sm uppercase text-on-surface">
          {setting.label}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={setting.value}
          aria-labelledby={labelId}
          aria-describedby={describedBy}
          onClick={() => onChange(!setting.value)}
          className={`mt-2 inline-flex h-6 w-11 items-center rounded-pill transition-colors duration-200 motion-reduce:transition-none ${
            setting.value ? "bg-primary" : "bg-outline"
          }`}
        >
          <span
            aria-hidden="true"
            className={`h-5 w-5 rounded-pill bg-surface-container-lowest shadow-sm transition-transform duration-200 motion-reduce:transition-none ${
              setting.value ? "translate-x-5" : "translate-x-0.5"
            }`}
          />
        </button>
        {hasDescription && (
          <p id={descriptionId} className="mt-1 text-caption text-on-surface-variant">
            {setting.description}
          </p>
        )}
      </div>
    );
  }

  if (setting.type === "number") {
    return (
      <div>
        <label htmlFor={inputId} className="block font-label text-label-sm uppercase text-on-surface">
          {setting.label}
          {setting.unit && <span className="font-normal"> ({setting.unit})</span>}
        </label>
        <input
          id={inputId}
          type="number"
          // `value=""` (never `NaN`/`0`) is what makes a null/"not
          // configured" numeric setting render as a genuinely empty
          // field instead of a misleading zero.
          value={setting.value === null ? "" : setting.value}
          min={setting.min}
          max={setting.max}
          step={setting.step}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value === "" ? null : event.target.valueAsNumber)}
          className={`mt-2 ${fieldControlClasses(false)}`}
        />
        {hasDescription && (
          <p id={descriptionId} className="mt-1 text-caption text-on-surface-variant">
            {setting.description}
          </p>
        )}
      </div>
    );
  }

  if (setting.type === "money") {
    return (
      <MoneyInput
        label={setting.label}
        hint={setting.description}
        currencyLabel={setting.value?.currency ?? "USD"}
        valueCents={setting.value?.amountCents ?? null}
        onChangeCents={(cents) =>
          onChange(cents === null ? null : { amountCents: cents, currency: setting.value?.currency ?? "USD" })
        }
      />
    );
  }

  if (setting.type === "json") {
    // No V1 setting actually has this type — a minimal, honest
    // non-editable fallback rather than a raw JSON textarea editor.
    return (
      <div>
        <span className="font-label text-label-sm uppercase text-on-surface">{setting.label}</span>
        <p className="mt-1 text-caption text-on-surface-variant">
          This setting can&rsquo;t be edited from this screen.
        </p>
      </div>
    );
  }

  return (
    <TextField
      label={setting.label}
      hint={setting.description}
      value={setting.value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
