"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { SettingControl } from "./SettingControl";
import type { EditableSetting, EditableSettingValue } from "./settingTypes";

export type SettingRowStatus = "idle" | "saving" | "saved" | "error";

export interface SettingRowProps {
  setting: EditableSetting;
  onSave: (nextValue: EditableSettingValue) => void;
  // External, already-safe status/message — a future API-adapter/mutation
  // hook owns deciding these (see settingTypes.ts's own
  // #ARCHITECTURE-SETTINGS-ADAPTER note); this component never parses a
  // raw backend error or awaits onSave's return value itself.
  status?: SettingRowStatus;
  errorMessage?: string;
}

// #FVS007-SETTINGS-EDITOR
//
// Owns only the ephemeral DRAFT value of its own open row (never
// persisted beyond this mounted component — no browser storage). Save/
// saving/saved/error presentation is entirely driven by external props,
// since the real pending/error state will live in a future TanStack
// mutation hook, not here.
export function SettingRow({ setting, onSave, status = "idle", errorMessage }: SettingRowProps) {
  const [draftValue, setDraftValue] = useState<EditableSettingValue>(setting.value);
  const draftSetting = { ...setting, value: draftValue } as EditableSetting;

  function handleSave() {
    onSave(draftValue);
  }

  return (
    <div data-testid="setting-row" className="flex flex-col gap-3 border-b border-border-default py-4 tablet:flex-row tablet:items-start tablet:justify-between">
      <SettingControl setting={draftSetting} onChange={setDraftValue} />
      <div className="flex items-center gap-2">
        <Button onClick={handleSave} isLoading={status === "saving"}>
          Save
        </Button>
        {status === "saved" && <span className="text-caption text-success">Saved</span>}
      </div>
      {status === "error" && errorMessage && <Alert variant="error" message={errorMessage} />}
    </div>
  );
}
