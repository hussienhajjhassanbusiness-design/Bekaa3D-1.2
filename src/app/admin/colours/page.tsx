"use client";

import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";
import type { ReferenceDataEntityConfig } from "@/components/admin/referenceDataTypes";

// No swatch/hex field: the real `Colour` resource has only `name` and
// `is_active` (docs/backend-handoff/BACKEND-RESPONSE.md P1-5) — unlike
// ReferenceDataManager's own generic test fixture, this page never
// enables hasSwatchField, since there is no colour-value field to edit.
const COLOUR_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Colour",
  entityLabelPlural: "Colours",
  emptyStateMessage: "No colours yet — create one.",
};

export default function AdminColoursPage() {
  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Colours</h1>
      <div className="mt-4">
        <AdminReferenceDataPage resource="colours" config={COLOUR_CONFIG} />
      </div>
    </>
  );
}
