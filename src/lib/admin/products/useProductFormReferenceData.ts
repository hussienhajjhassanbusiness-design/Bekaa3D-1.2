import { useReferenceDataList } from "@/lib/admin/referenceData/useReferenceData";
import type { ProductFormOption } from "@/components/admin/ProductForm";

// ProductForm's category/material/colour dropdowns offer every
// not-archived value (live or disabled) — a permanently archived value
// can no longer be meaningfully assigned to a product, but a merely
// disabled one still can be (disabling only affects public filter
// visibility, not admin assignability).
function toOptions(entries: readonly { id: string; name: string; isArchived: boolean }[] | undefined): ProductFormOption[] {
  return (entries ?? []).filter((entry) => !entry.isArchived).map((entry) => ({ id: entry.id, name: entry.name }));
}

export function useProductFormReferenceData() {
  const categories = useReferenceDataList("categories", false);
  const materials = useReferenceDataList("materials", false);
  const colours = useReferenceDataList("colours", false);

  return {
    categories: toOptions(categories.data),
    materials: toOptions(materials.data),
    colours: toOptions(colours.data),
    isLoading: categories.isLoading || materials.isLoading || colours.isLoading,
  };
}
