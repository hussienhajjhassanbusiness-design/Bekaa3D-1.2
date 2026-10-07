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
    <span className="inline-block rounded-pill bg-neutral-100 px-2 py-0.5 text-caption font-semibold text-text-primary">
      {LABELS[type]}
    </span>
  );
}
