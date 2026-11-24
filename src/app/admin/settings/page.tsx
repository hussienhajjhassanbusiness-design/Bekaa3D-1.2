"use client";

import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { SettingControl } from "@/components/admin/settings/SettingControl";
import type { EditableSetting, EditableSettingValue } from "@/components/admin/settings/settingTypes";
import { useAdminSettings } from "@/lib/admin/settings/useAdminSettings";
import { useAdminSettingUpdate } from "@/lib/admin/settings/useAdminSettingUpdate";
import { toEditableSetting, toPatchValue } from "@/lib/admin/settings/settingsAdapter";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";

const LOAD_ERROR_MESSAGE = "Couldn't load settings. Please try again.";
const SAVED_MESSAGE = "Settings saved.";
const SAVING_MESSAGE = "Saving…";
const ALL_FAILED_MESSAGE = "Your changes couldn't be saved. Review the highlighted settings and try again.";
const PARTIAL_FAILURE_MESSAGE =
  "Some changes were saved, but others couldn't be. Review the highlighted settings and try again.";

// Business settings this screen's admin should confirm before applying
// — today that's just `accepting_orders`, the checkout kill switch
// (AGENTS.md: "deserves a confirmation UX because it globally affects
// checkout availability"). No other key is flagged confirm-worthy.
const KEYS_REQUIRING_CONFIRMATION = new Set(["accepting_orders"]);

// Presentation-only grouping of the keys the backend registry returns.
// A key listed here but absent from the server response simply doesn't
// render; any server key not listed lands in "Other settings", so the
// form never hides a real setting and never invents one.
const SECTIONS: { id: string; title: string; keys: string[] }[] = [
  { id: "availability", title: "Store availability", keys: ["accepting_orders"] },
  { id: "payments", title: "Payments", keys: ["cash_payment_enabled", "cash_max_order_total", "cash_max_open_orders"] },
  { id: "pickup", title: "Pickup", keys: ["pickup_address", "pickup_hours"] },
  { id: "contact", title: "Contact", keys: ["whatsapp_number"] },
];
const SECTIONED_KEYS = new Set(SECTIONS.flatMap((section) => section.keys));

type SettingValues = Record<string, EditableSettingValue>;

type SaveState =
  { status: "idle" } | { status: "saving" } | { status: "saved" } | { status: "error"; partial: boolean };

// Setting values are primitives or small plain objects (money), so a
// JSON comparison is an exact, order-stable equality check here.
function sameValue(a: EditableSettingValue, b: EditableSettingValue): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

function valuesOf(settings: EditableSetting[]): SettingValues {
  return Object.fromEntries(settings.map((setting) => [setting.key, setting.value]));
}

// The settings PATCH is per key (`PATCH /api/v1/admin/settings/{key}`,
// body `{ value }` only — no bulk endpoint), so one "Save changes" sends
// one request per CHANGED key, sequentially, and tracks each outcome:
// a key's saved snapshot only moves once the server confirmed it.
export default function AdminSettingsPage() {
  const { data: settings, isLoading, isError } = useAdminSettings();
  const updateMutation = useAdminSettingUpdate();

  // `baseline` = last server-confirmed value per key; `draft` = what the
  // form shows. A key is dirty when the two differ.
  const [baseline, setBaseline] = useState<SettingValues>({});
  const [draft, setDraft] = useState<SettingValues>({});
  const [syncedSettings, setSyncedSettings] = useState<EditableSetting[] | undefined>(undefined);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [confirmOpen, setConfirmOpen] = useState(false);
  const savingRef = useRef(false);

  // Fresh server data (first load, a refetch, another admin's change)
  // re-bases the form: clean fields adopt the server value, while a
  // field with an unsaved edit keeps the admin's edit on screen.
  if (settings && settings !== syncedSettings) {
    const serverValues = valuesOf(settings);
    const nextDraft: SettingValues = {};
    for (const key of Object.keys(serverValues)) {
      const isEdited = key in draft && !sameValue(draft[key], baseline[key]);
      nextDraft[key] = isEdited ? draft[key] : serverValues[key];
    }
    setSyncedSettings(settings);
    setBaseline(serverValues);
    setDraft(nextDraft);
  }

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError || !settings) {
    return <Alert variant="error" message={LOAD_ERROR_MESSAGE} />;
  }

  const settingsByKey = new Map(settings.map((setting) => [setting.key, setting]));
  const changedKeys = settings
    .map((setting) => setting.key)
    .filter((key) => key in draft && !sameValue(draft[key], baseline[key]));
  const isDirty = changedKeys.length > 0;
  const isSaving = saveState.status === "saving";

  const sections = [
    ...SECTIONS.map((section) => ({
      ...section,
      settings: section.keys.flatMap((key) => settingsByKey.get(key) ?? []),
    })),
    {
      id: "other",
      title: "Other settings",
      keys: [],
      settings: settings.filter((setting) => !SECTIONED_KEYS.has(setting.key)),
    },
  ].filter((section) => section.settings.length > 0);

  function handleChange(key: string, value: EditableSettingValue) {
    setDraft((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => {
      if (!(key in current)) return current;
      const rest = { ...current };
      delete rest[key];
      return rest;
    });
    if (saveState.status === "saved") {
      setSaveState({ status: "idle" });
    }
  }

  async function saveChanges(keys: string[]) {
    if (savingRef.current || keys.length === 0) return;
    savingRef.current = true;
    setSaveState({ status: "saving" });
    setFieldErrors({});

    const errors: Record<string, string> = {};
    let savedCount = 0;
    for (const key of keys) {
      const setting = settingsByKey.get(key);
      if (!setting) continue;
      try {
        const saved = await updateMutation.mutateAsync({ key, value: toPatchValue(setting, draft[key]) });
        // Reconcile with what the server actually stored, not with what
        // was sent.
        const savedValue = toEditableSetting(saved).value;
        setBaseline((current) => ({ ...current, [key]: savedValue }));
        setDraft((current) => ({ ...current, [key]: savedValue }));
        savedCount += 1;
      } catch (error) {
        errors[key] = describeAdminError(error);
      }
    }

    savingRef.current = false;
    setFieldErrors(errors);
    setSaveState(Object.keys(errors).length === 0 ? { status: "saved" } : { status: "error", partial: savedCount > 0 });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isDirty || savingRef.current) return;
    if (changedKeys.some((key) => KEYS_REQUIRING_CONFIRMATION.has(key))) {
      setConfirmOpen(true);
      return;
    }
    void saveChanges(changedKeys);
  }

  function handleDiscard() {
    setDraft(baseline);
    setFieldErrors({});
    setSaveState({ status: "idle" });
  }

  const statusMessage =
    saveState.status === "saving" ? SAVING_MESSAGE : saveState.status === "saved" ? SAVED_MESSAGE : "";

  return (
    <>
      <PageHeader title="Settings" description="Edit any store settings below, then save them together." />

      <form noValidate onSubmit={handleSubmit} aria-label="Store settings form" className="max-w-form">
        <fieldset disabled={isSaving} className="space-y-6">
          {sections.map((section) => (
            <section
              key={section.id}
              aria-labelledby={`settings-section-${section.id}`}
              className="rounded-card border border-outline-variant/40 bg-surface-container-lowest px-5 shadow-sm tablet:px-6"
            >
              <h2
                id={`settings-section-${section.id}`}
                className="border-b border-outline-variant/30 py-4 font-headline text-headline-md text-on-surface"
              >
                {section.title}
              </h2>
              <div className="divide-y divide-outline-variant/30">
                {section.settings.map((setting) => {
                  const fieldError = fieldErrors[setting.key];
                  const value = setting.key in draft ? draft[setting.key] : setting.value;
                  return (
                    <div key={setting.key} data-testid="setting-row" className="flex flex-col gap-3 py-5">
                      <SettingControl
                        setting={{ ...setting, value } as EditableSetting}
                        onChange={(next) => handleChange(setting.key, next)}
                      />
                      {fieldError && <Alert variant="error" message={fieldError} />}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </fieldset>

        {saveState.status === "error" && (
          <div className="mt-6">
            <Alert variant="error" message={saveState.partial ? PARTIAL_FAILURE_MESSAGE : ALL_FAILED_MESSAGE} />
          </div>
        )}

        <div className="mt-6 flex flex-col gap-3 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-4 shadow-sm tablet:flex-row tablet:items-center tablet:justify-between tablet:px-6">
          <div className="min-h-5 font-label text-label-sm text-on-surface-variant">
            {/* One persistent polite region, so "Saving…" / "Settings
                saved." are announced once each — field edits never are. */}
            <p role="status" aria-live="polite" className="inline-flex items-center gap-1">
              {saveState.status === "saved" && <Icon name="check-circle" className="h-4 w-4 text-primary" />}
              {statusMessage}
            </p>
            {isDirty && !isSaving && saveState.status !== "saved" && <span>Unsaved changes</span>}
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={handleDiscard} disabled={!isDirty || isSaving}>
              Discard changes
            </Button>
            <Button type="submit" disabled={!isDirty} isLoading={isSaving}>
              Save changes
            </Button>
          </div>
        </div>
      </form>

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
        open={confirmOpen}
        title="Change checkout availability"
        description="This immediately changes whether customers can place new orders. Are you sure?"
        confirmLabel="Confirm change"
        isConfirming={isSaving}
        onConfirm={() => {
          setConfirmOpen(false);
          void saveChanges(changedKeys);
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
