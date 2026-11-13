export type ProductTypeUi = "physical" | "stl";

export interface ProductTypeBadgeProps {
  type: ProductTypeUi;
}

// Internal frontend UI literals — mirror FVS-011's ProductTypeSelector
// vocabulary without importing that admin-scoped module (public catalog
// code should not depend on an admin component's type). NOT a claim
// about the backend's real discriminator field name or enum strings
// (FVS-014-IMPLEMENTATION-PLAN.md §1). Text-only, never icon/color
// alone.
const LABELS: Record<ProductTypeUi, string> = {
  physical: "Physical",
  stl: "STL",
};

export function ProductTypeBadge({ type }: ProductTypeBadgeProps) {
  return (
    // Stitch format tag (COMPONENT-SPECS §18): 4px badge radius, mono label.
    <span className="inline-flex items-center rounded-badge bg-surface-container-highest px-2 py-1 font-label text-label-sm font-bold uppercase leading-4 text-on-surface-variant">
      {LABELS[type]}
    </span>
  );
}
