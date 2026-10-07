"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/forms/Button";
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
  isLoading?: boolean;
  isSaving?: boolean;
  isArchiving?: boolean;
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
  isLoading = false,
  isSaving = false,
  isArchiving = false,
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
    <section>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-h3 font-bold text-text-primary">{config.entityLabelPlural}</h2>
        <Button type="button" onClick={openCreate}>
          Add {config.entityLabelSingular}
        </Button>
      </div>

      {isLoading ? (
        <div role="status">
          <span className="sr-only">Loading…</span>
        </div>
      ) : entries.length === 0 ? (
        <p className="mt-4 text-body text-text-secondary">{config.emptyStateMessage}</p>
      ) : (
        <ul className="mt-4">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-col gap-3 border-b border-border-default py-4 tablet:flex-row tablet:items-center tablet:justify-between"
            >
              <div className="flex items-center gap-2">
                {config.renderSwatch && entry.swatchValue && config.renderSwatch(entry.swatchValue)}
                <span className="text-body text-text-primary">{entry.name}</span>
                {entry.isArchived && (
                  <span className="rounded-pill bg-neutral-200 px-2 py-0.5 text-caption font-semibold text-text-secondary">
                    Archived
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" onClick={() => openEdit(entry)}>
                  Edit
                </Button>
                <Button type="button" onClick={() => setArchiveTargetId(entry.id)} disabled={entry.isArchived}>
                  Archive
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {formMode.kind !== "closed" && (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
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
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={isSaving} isLoading={isSaving}>
              Save
            </Button>
            <Button type="button" onClick={closeForm}>
              Cancel
            </Button>
          </div>
        </form>
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
