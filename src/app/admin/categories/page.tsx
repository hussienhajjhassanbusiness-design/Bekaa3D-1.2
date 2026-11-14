"use client";

import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";
import type { ReferenceDataEntityConfig } from "@/components/admin/referenceDataTypes";

const CATEGORY_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Category",
  entityLabelPlural: "Categories",
  emptyStateMessage: "No categories yet — create one.",
  hasSwatchField: true,
  swatchFieldLabel: "Slug",
  renderSwatch: (value) => <span className="font-label text-label-sm text-on-surface-variant">/{value}</span>,
};

export default function AdminCategoriesPage() {
  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Categories</h1>
      <div className="mt-4">
        <AdminReferenceDataPage resource="categories" config={CATEGORY_CONFIG} />
      </div>
    </>
  );
}
