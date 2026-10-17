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
      <h1 className="text-h1 font-bold text-text-primary">Materials</h1>
      <div className="mt-4">
        <AdminReferenceDataPage resource="materials" config={MATERIAL_CONFIG} />
      </div>
    </>
  );
}
