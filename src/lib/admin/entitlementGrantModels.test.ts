import { describe, it, expect } from "vitest";
import { selectableStlProducts, type ProductOption } from "./entitlementGrantModels";

// FVS-019-IMPLEMENTATION-PLAN.md T01 — reuses FVS-011's own
// `ProductTypeOption` ("physical" | "stl") rather than inventing a
// third, incompatible product-type union (audited first — see plan
// §0). #SECURITY-ENTITLEMENT-GRANT: this filter is UX-only; the server
// remains the sole authority and MUST independently reject a grant for
// a non-STL product regardless of what this function ever returns.

function makeProduct(overrides: Partial<ProductOption> = {}): ProductOption {
  return { id: "p-1", displayLabel: "Widget", productType: "stl", ...overrides };
}

describe("selectableStlProducts", () => {
  it("includes an STL product", () => {
    const stl = makeProduct({ id: "p-1", productType: "stl" });
    expect(selectableStlProducts([stl])).toEqual([stl]);
  });

  it("excludes a physical product", () => {
    const physical = makeProduct({ id: "p-2", productType: "physical" });
    expect(selectableStlProducts([physical])).toEqual([]);
  });

  it("filters a mixed list down to only STL products", () => {
    const stl = makeProduct({ id: "p-1", productType: "stl" });
    const physical = makeProduct({ id: "p-2", productType: "physical" });
    expect(selectableStlProducts([stl, physical])).toEqual([stl]);
  });

  it("does not mutate the input array", () => {
    const products = [makeProduct({ id: "p-1", productType: "stl" }), makeProduct({ id: "p-2", productType: "physical" })];
    const original = [...products];

    selectableStlProducts(products);

    expect(products).toEqual(original);
  });
});
