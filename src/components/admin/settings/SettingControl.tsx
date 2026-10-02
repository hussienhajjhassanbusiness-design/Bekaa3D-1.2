"use client";

import { useId } from "react";
import { TextField } from "@/components/forms/TextField";
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
        <span id={labelId} className="text-label font-semibold uppercase tracking-label text-text-primary">
          {setting.label}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={setting.value}
          aria-labelledby={labelId}
          aria-describedby={describedBy}
          onClick={() => onChange(!setting.value)}
          className={`mt-1 inline-flex h-6 w-11 items-center rounded-pill border border-border-default transition-colors ${
            setting.value ? "bg-brand-dark-green" : "bg-neutral-200"
          }`}
        >
          <span
            aria-hidden="true"
            className={`h-5 w-5 rounded-pill bg-white transition-transform ${
              setting.value ? "translate-x-5" : "translate-x-0.5"
            }`}
          />
        </button>
        {hasDescription && (
          <p id={descriptionId} className="mt-1 text-caption text-text-secondary">
            {setting.description}
          </p>
        )}
      </div>
    );
  }

  if (setting.type === "number") {
    return (
      <div>
        <label htmlFor={inputId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          {setting.label}
        </label>
        <input
          id={inputId}
          type="number"
          value={setting.value}
          min={setting.min}
          max={setting.max}
          step={setting.step}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.valueAsNumber)}
          className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
        />
        {hasDescription && (
          <p id={descriptionId} className="mt-1 text-caption text-text-secondary">
            {setting.description}
          </p>
        )}
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
