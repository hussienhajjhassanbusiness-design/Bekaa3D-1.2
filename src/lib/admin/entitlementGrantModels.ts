import type { ProductTypeOption } from "@/components/admin/ProductTypeSelector";

// Frontend-only normalized option models — NOT a claim about any
// backend DTO field name (FVS-019-IMPLEMENTATION-PLAN.md §1). Reuses
// FVS-011's own `ProductTypeOption` ("physical" | "stl") instead of
// introducing a third, incompatible product-type union — audited
// first (plan §0): this is admin-scoped code importing an admin-scoped
// type, unlike FVS-014's public catalog code, which deliberately did
// NOT import from `admin/`.
export interface CustomerOption {
  id: string;
  displayLabel: string;
}

export interface ProductOption {
  id: string;
  displayLabel: string;
  productType: ProductTypeOption;
}

// #SECURITY-ENTITLEMENT-GRANT
//
// UX-only filter. The server remains the sole authority and MUST
// independently reject a grant for a non-STL product regardless of
// what this function ever returns — hiding physical products from the
// picker is never treated as an authorization boundary
// (vertical-slice-plan.md VS-017: "Only STL" is a server-side test).
export function selectableStlProducts(products: readonly ProductOption[]): ProductOption[] {
  return products.filter((product) => product.productType === "stl");
}
