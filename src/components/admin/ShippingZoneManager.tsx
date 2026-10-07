"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";
import { MoneyInput } from "@/components/forms/MoneyInput";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import type { ShippingZoneAdminModel } from "@/lib/shippingZones/shippingZoneModels";

export interface ShippingZoneDraft {
  displayName: string;
  rateCents: number | null;
}

export type ShippingZoneFieldErrors = Partial<Record<"displayName" | "rateCents", string>>;

export interface ShippingZoneManagerProps {
  zones: readonly ShippingZoneAdminModel[];
  // Caller-supplied, never hardcoded — "Confirm USD settlement/support"
  // remains an explicitly open external item (vertical-slice-plan.md
  // §2). No currency-picker UI exists this batch (no evidence one is
  // needed); every zone created/edited here uses this one value.
  currency: string;
  onSave: (draft: ShippingZoneDraft, editingId: string | null) => void;
  onArchive: (zoneId: string) => void;
  isLoading?: boolean;
  isSaving?: boolean;
  isArchiving?: boolean;
  fieldErrors?: ShippingZoneFieldErrors;
}

type FormMode = { kind: "closed" } | { kind: "create" } | { kind: "edit"; zoneId: string };

const EMPTY_MESSAGE = "No shipping zones yet — create one.";

// #FVS024-SHIPPING-ZONE-MANAGER
//
// A focused component, not a forced ReferenceDataManager extension —
// money doesn't fit that component's string-only draft shape
// (FVS-024-IMPLEMENTATION-PLAN.md §0) — but reuses the exact same
// responsive stacked-card / inline-form / ConfirmDialog-archive
// pattern. Rate editing reuses MoneyInput directly (cents-safe,
// string-based parsing — never `parseFloat(value) * 100`); rate
// display reuses PriceDisplay — neither is duplicated here.
//
// #SECURITY-SERVER-SHIPPING-RATE-AUTHORITY — this component only
// displays/edits values the server will authoritatively validate; it
// never computes a shipping price, a zone match, or a free-shipping
// decision itself. #ARCHITECTURE-EXPLICIT-SHIPPING-ZONE — no
// address/governorate field exists anywhere here. Archiving a zone
// here never touches a past order's immutable snapshot
// (#ARCHITECTURE-SHIPPING-SNAPSHOT-IMMUTABLE) — this component has no
// order-related code at all, by design.
export function ShippingZoneManager({
  zones,
  currency,
  onSave,
  onArchive,
  isLoading = false,
  isSaving = false,
  isArchiving = false,
  fieldErrors,
}: ShippingZoneManagerProps) {
  const [formMode, setFormMode] = useState<FormMode>({ kind: "closed" });
  const [draftName, setDraftName] = useState("");
  const [draftRateCents, setDraftRateCents] = useState<number | null>(null);
  const [archiveTargetId, setArchiveTargetId] = useState<string | null>(null);

  function openCreate() {
    setDraftName("");
    setDraftRateCents(null);
    setFormMode({ kind: "create" });
  }

  function openEdit(zone: ShippingZoneAdminModel) {
    setDraftName(zone.displayName);
    setDraftRateCents(zone.rateCents);
    setFormMode({ kind: "edit", zoneId: zone.id });
  }

  function closeForm() {
    setFormMode({ kind: "closed" });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const draft: ShippingZoneDraft = { displayName: draftName, rateCents: draftRateCents };
    onSave(draft, formMode.kind === "edit" ? formMode.zoneId : null);
  }

  return (
    <section>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-h3 font-bold text-text-primary">Shipping Zones</h2>
        <Button type="button" onClick={openCreate}>
          Add Zone
        </Button>
      </div>

      {isLoading ? (
        <div role="status">
          <span className="sr-only">Loading…</span>
        </div>
      ) : zones.length === 0 ? (
        <p className="mt-4 text-body text-text-secondary">{EMPTY_MESSAGE}</p>
      ) : (
        <ul className="mt-4">
          {zones.map((zone) => (
            <li
              key={zone.id}
              className="flex flex-col gap-3 border-b border-border-default py-4 tablet:flex-row tablet:items-center tablet:justify-between"
            >
              <div className="flex items-center gap-2">
                <span className="text-body text-text-primary">{zone.displayName}</span>
                <PriceDisplay amountCents={zone.rateCents} currency={zone.currency} />
                {zone.isArchived && (
                  <span className="rounded-pill bg-neutral-200 px-2 py-0.5 text-caption font-semibold text-text-secondary">
                    Archived
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" onClick={() => openEdit(zone)}>
                  Edit
                </Button>
                <Button type="button" onClick={() => setArchiveTargetId(zone.id)} disabled={zone.isArchived}>
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
            error={fieldErrors?.displayName}
          />
          <MoneyInput
            label="Rate"
            currencyLabel={currency}
            valueCents={draftRateCents}
            onChangeCents={setDraftRateCents}
            hint={fieldErrors?.rateCents}
          />
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
        title="Archive shipping zone"
        description="This zone will be archived. It stays visible here but is excluded from checkout."
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
