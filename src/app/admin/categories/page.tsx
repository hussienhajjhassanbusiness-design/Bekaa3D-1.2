"use client";

import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";
import type { ReferenceDataEntityConfig } from "@/components/admin/referenceDataTypes";

// Lifecycle copy follows the backend's rules (backend docs/reference-data.md):
// disabled = hidden publicly, re-enabled with PATCH; archived = DELETE, a soft
// delete that releases the slug, is refused while a live product uses the
// category (409 CATEGORY_IN_USE), and is terminal: no restore endpoint, and
// PATCH on an archived row answers 409 INVALID_STATE_TRANSITION.
const CATEGORY_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Category",
  entityLabelPlural: "Categories",
  emptyStateMessage: "No categories yet — create one.",
  hasSwatchField: true,
  swatchFieldLabel: "Slug",
  renderSwatch: (value) => <span className="font-label text-label-sm text-on-surface-variant">/{value}</span>,
  lifecycle: {
    archiveConsequences: [
      "It disappears from the storefront and can no longer be chosen for products.",
      "Its slug is released, so a new category can reuse it.",
      "It can't be edited, enabled or restored afterwards. To hide it for now, disable it instead.",
      "Nothing is deleted. A category that a live product still uses can't be archived: move those products to another category first.",
    ],
    archivedNote:
      "Archived categories are kept for the record. They can't be edited or restored in this version of the admin.",
    emptyMessages: {
      active: "No active categories.",
      disabled: "No disabled categories. Disable a category to hide it from the storefront without archiving it.",
      archived: "No archived categories.",
    },
  },
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
