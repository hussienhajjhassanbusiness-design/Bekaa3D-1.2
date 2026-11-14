"use client";

import { buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { useState } from "react";
import Link from "next/link";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { SettingRow, type SettingRowStatus } from "@/components/admin/settings/SettingRow";
import type { EditableSetting, EditableSettingValue } from "@/components/admin/settings/settingTypes";
import { useAdminSettings } from "@/lib/admin/settings/useAdminSettings";
import { useAdminSettingUpdate } from "@/lib/admin/settings/useAdminSettingUpdate";
import { toPatchValue } from "@/lib/admin/settings/settingsAdapter";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";

const LOAD_ERROR_MESSAGE = "Couldn't load settings. Please try again.";

// Business settings this screen's admin should confirm before applying
// — today that's just `accepting_orders`, the checkout kill switch
// (AGENTS.md: "deserves a confirmation UX because it globally affects
// checkout availability"). No other key is flagged confirm-worthy.
const KEYS_REQUIRING_CONFIRMATION = new Set(["accepting_orders"]);

interface RowState {
  status: SettingRowStatus;
  errorMessage?: string;
}

export default function AdminSettingsPage() {
  const { data: settings, isLoading, isError } = useAdminSettings();
  const updateMutation = useAdminSettingUpdate();
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({});
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    setting: EditableSetting;
    value: EditableSettingValue;
  } | null>(null);

  function setRowState(key: string, state: RowState) {
    setRowStates((current) => ({ ...current, [key]: state }));
  }

  async function applySave(setting: EditableSetting, value: EditableSettingValue) {
    setRowState(setting.key, { status: "saving" });
    try {
      await updateMutation.mutateAsync({ key: setting.key, value: toPatchValue(setting, value) });
      setRowState(setting.key, { status: "saved" });
    } catch (error) {
      setRowState(setting.key, { status: "error", errorMessage: describeAdminError(error) });
    }
  }

  function handleSave(setting: EditableSetting, value: EditableSettingValue) {
    if (KEYS_REQUIRING_CONFIRMATION.has(setting.key)) {
      setPendingConfirmation({ setting, value });
      return;
    }
    void applySave(setting, value);
  }

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError || !settings) {
    return <Alert variant="error" message={LOAD_ERROR_MESSAGE} />;
  }

  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Settings</h1>
      <p className="mt-2 max-w-3xl font-body text-body-md text-on-surface-variant">
        Store settings take effect as soon as you save each one.
      </p>
      <div className="mt-6 max-w-form divide-y divide-outline-variant/30 rounded-card border border-outline-variant/40 bg-surface-container-lowest px-5 shadow-sm tablet:px-6">
        {settings.map((setting) => (
          <SettingRow
            key={setting.key}
            setting={setting}
            onSave={(value) => handleSave(setting, value)}
            status={rowStates[setting.key]?.status}
            errorMessage={rowStates[setting.key]?.errorMessage}
          />
        ))}
      </div>

      <section
        aria-labelledby="settings-security-heading"
        className="mt-6 max-w-form rounded-card border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm tablet:p-6"
      >
        <h2
          id="settings-security-heading"
          className="flex items-center gap-2 font-headline text-headline-md text-on-surface"
        >
          <Icon name="lock" className="h-5 w-5 text-primary" />
          Security
        </h2>
        <p className="mt-1 text-body-md text-on-surface-variant">
          Regenerate your two-factor recovery codes if you&rsquo;ve lost the current ones.
        </p>
        <Link href="/admin/mfa/recovery-codes" className={`${buttonLinkClassName("outline")} mt-4`}>
          Regenerate recovery codes
        </Link>
      </section>

      <ConfirmDialog
        open={pendingConfirmation !== null}
        title="Change checkout availability"
        description="This immediately changes whether customers can place new orders. Are you sure?"
        confirmLabel="Confirm change"
        isConfirming={pendingConfirmation !== null && rowStates[pendingConfirmation.setting.key]?.status === "saving"}
        onConfirm={() => {
          if (pendingConfirmation) {
            void applySave(pendingConfirmation.setting, pendingConfirmation.value);
          }
          setPendingConfirmation(null);
        }}
        onCancel={() => setPendingConfirmation(null)}
      />
    </>
  );
}
