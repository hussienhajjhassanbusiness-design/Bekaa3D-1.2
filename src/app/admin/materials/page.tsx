"use client";

import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";
import type { ReferenceDataEntityConfig } from "@/components/admin/referenceDataTypes";

const MATERIAL_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Material",
  entityLabelPlural: "Materials",
  emptyStateMessage: "No materials yet — create one.",
};

export default function AdminMaterialsPage() {
  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Materials</h1>
      <div className="mt-4">
        <AdminReferenceDataPage resource="materials" config={MATERIAL_CONFIG} />
      </div>
    </>
  );
}
