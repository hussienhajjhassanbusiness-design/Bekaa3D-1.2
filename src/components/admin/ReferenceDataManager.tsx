"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "./StatusBadge";
import { TextField } from "@/components/forms/TextField";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import type {
  ReferenceDataDraft,
  ReferenceDataEntityConfig,
  ReferenceDataEntry,
  ReferenceDataFieldErrors,
} from "./referenceDataTypes";

export interface ReferenceDataManagerProps {
  config: ReferenceDataEntityConfig;
  entries: readonly ReferenceDataEntry[];
  onSave: (draft: ReferenceDataDraft, editingId: string | null) => void;
  onArchive: (id: string) => void;
  // Reversible enable/disable (AGENTS.md: "PATCH is used for reversible
  // enable/disable", distinct from the permanent DELETE/archive below).
  // Optional: a caller with no such concept simply omits it, and this
  // row-level action never renders (archive-only behavior, unchanged).
  onToggleActive?: (id: string, nextIsActive: boolean) => void;
  isLoading?: boolean;
  isSaving?: boolean;
  isArchiving?: boolean;
  isTogglingActive?: boolean;
  fieldErrors?: ReferenceDataFieldErrors;
}

type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; entryId: string };

// #FVS010-REFERENCE-DATA
//
// One generic manager configured per entity (category/material/colour) —
// never branches internally on which entity it is rendering. Every
// per-entity difference (labels, empty-state copy, the optional
// supplemental swatch field) comes from `config`
// (#ARCHITECTURE-REFERENCE-DATA-ADAPTER in referenceDataTypes.ts).
//
// Presentational only: no fetch, no TanStack Query, no production
// mutation. The create/edit draft exists only for the current open
// interaction — no browser storage, no autosave. Archive reuses the
// existing ConfirmDialog (FVS-007) rather than a new modal; the UI intent
// is always "Archive" (soft, reversible-sounding), never "Delete" —
// backend DELETE semantics are not assumed to mean hard deletion
// (FVS-010-IMPLEMENTATION-PLAN.md §1).
//
// Uses the FVS-007 stacked-card responsive pattern (flex-col below
// tablet, flex-row at tablet+), NOT AdminTable's horizontal-scroll table
// — FRONTEND-VERTICAL-SLICE-PLAN.md §14 explicitly reserves the
// stacked-card fallback for exactly this kind of simple reference-data
// list, distinct from AdminTable's own larger-list pattern (FVS-009).
//
// Archived state is conveyed as visible text ("Archived"), never color
// alone. FVS-009's StatusBadge ("active"/"deactivated") is deliberately
// NOT reused here — its two-value customer-account vocabulary doesn't
// fit a reference-data archive concept, and forcing it would misuse a
// differently-scoped shared component rather than genuinely generalize
// it; a plain text badge is simpler and correct for this one need.
export function ReferenceDataManager({
  config,
  entries,
  onSave,
  onArchive,
  onToggleActive,
  isLoading = false,
  isSaving = false,
  isArchiving = false,
  isTogglingActive = false,
  fieldErrors,
}: ReferenceDataManagerProps) {
  const [formMode, setFormMode] = useState<FormMode>({ kind: "closed" });
  const [draftName, setDraftName] = useState("");
  const [draftSwatchValue, setDraftSwatchValue] = useState("");
  const [archiveTargetId, setArchiveTargetId] = useState<string | null>(null);

  function openCreate() {
    setDraftName("");
    setDraftSwatchValue("");
    setFormMode({ kind: "create" });
  }

  function openEdit(entry: ReferenceDataEntry) {
    setDraftName(entry.name);
    setDraftSwatchValue(entry.swatchValue ?? "");
    setFormMode({ kind: "edit", entryId: entry.id });
  }

  function closeForm() {
    setFormMode({ kind: "closed" });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const draft: ReferenceDataDraft = { name: draftName };
    if (config.hasSwatchField) {
      draft.swatchValue = draftSwatchValue;
    }
    onSave(draft, formMode.kind === "edit" ? formMode.entryId : null);
  }

  return (
    <section className="overflow-hidden rounded-card border border-outline-variant/40 bg-surface-container-lowest shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/40 px-4 py-4 tablet:px-6">
        <h2 className="font-headline text-headline-md text-on-surface">{config.entityLabelPlural}</h2>
        <Button type="button" onClick={openCreate}>
          <Icon name="add" className="h-5 w-5" />
          Add {config.entityLabelSingular}
        </Button>
      </div>

      {formMode.kind !== "closed" && (
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 border-b border-outline-variant/40 bg-surface-container-low px-4 py-6 tablet:px-6"
        >
          <div className="grid gap-4 tablet:grid-cols-2">
            <TextField
              label="Name"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              error={fieldErrors?.name}
            />
            {config.hasSwatchField && (
              <TextField
                label={config.swatchFieldLabel ?? "Value"}
                value={draftSwatchValue}
                onChange={(event) => setDraftSwatchValue(event.target.value)}
                error={fieldErrors?.swatchValue}
              />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={isSaving} isLoading={isSaving}>
              Save
            </Button>
            <Button type="button" variant="outline" onClick={closeForm}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div role="status" className="flex flex-col gap-3 p-4 tablet:p-6">
          <span className="sr-only">Loading…</span>
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              aria-hidden="true"
              className="h-10 animate-pulse rounded-control bg-surface-container-low motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="px-6 py-12 text-center font-body text-body-md text-on-surface-variant">
          {config.emptyStateMessage}
        </p>
      ) : (
        <ul className="divide-y divide-outline-variant/30">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-col gap-3 px-4 py-4 tablet:flex-row tablet:items-center tablet:justify-between tablet:px-6"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                {config.renderSwatch && entry.swatchValue && config.renderSwatch(entry.swatchValue)}
                <span className="break-words font-body text-body-md font-semibold text-on-surface">{entry.name}</span>
                {entry.isArchived && <StatusBadge label="Archived" tone="neutral" />}
                {!entry.isArchived && entry.isActive === false && <StatusBadge label="Disabled" tone="warning" />}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" className="min-h-11" onClick={() => openEdit(entry)}>
                  Edit
                </Button>
                {onToggleActive && !entry.isArchived && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-11"
                    disabled={isTogglingActive}
                    onClick={() => onToggleActive(entry.id, entry.isActive === false)}
                  >
                    {entry.isActive === false ? "Enable" : "Disable"}
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-11 text-error"
                  onClick={() => setArchiveTargetId(entry.id)}
                  disabled={entry.isArchived}
                >
                  Archive
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={archiveTargetId !== null}
        title={`Archive ${config.entityLabelSingular}`}
        description={`This ${config.entityLabelSingular.toLowerCase()} will be archived. It stays visible here but is excluded from public use.`}
        confirmLabel="Archive"
        isConfirming={isArchiving}
        onConfirm={() => {
          if (archiveTargetId) {
            onArchive(archiveTargetId);
          }
        }}
        onCancel={() => setArchiveTargetId(null)}
      />
    </section>
  );
}
