import { describe, it, expect } from "vitest";
import { toProductsQueryParams } from "./shopQueryAdapter";
import type { ShopUrlState } from "./shopUrlState";

function urlState(overrides: Partial<ShopUrlState> = {}): ShopUrlState {
  return { category: [], material: [], colour: [], sort: null, q: "", cursor: null, ...overrides };
}

describe("toProductsQueryParams", () => {
  it("maps an empty URL state to empty query params", () => {
    expect(toProductsQueryParams(urlState())).toEqual({});
  });

  it("maps the one selected category value to category_id — never the plural 'category' key", () => {
    const params = toProductsQueryParams(urlState({ category: ["cat-uuid"] }));
    expect(params).toEqual({ category_id: "cat-uuid" });
  });

  it("maps material and colour the same way", () => {
    const params = toProductsQueryParams(urlState({ material: ["mat-uuid"], colour: ["col-uuid"] }));
    expect(params).toEqual({ material_id: "mat-uuid", colour_id: "col-uuid" });
  });

  it("passes q through unchanged", () => {
    expect(toProductsQueryParams(urlState({ q: "dragon" }))).toEqual({ q: "dragon" });
  });

  it("passes a recognized sort value through unchanged", () => {
    expect(toProductsQueryParams(urlState({ sort: "-price" }))).toEqual({ sort: "-price" });
  });

  it("omits an unrecognized sort value rather than sending a value the backend would reject", () => {
    expect(toProductsQueryParams(urlState({ sort: "most-downloaded" }))).toEqual({});
  });

  it("passes cursor through unchanged, still opaque", () => {
    expect(toProductsQueryParams(urlState({ cursor: "opaque-token" }))).toEqual({ cursor: "opaque-token" });
  });

  it("combines every set field", () => {
    const params = toProductsQueryParams(
      urlState({ category: ["cat-uuid"], q: "dragon", sort: "-created_at", cursor: "tok" })
    );
    expect(params).toEqual({ category_id: "cat-uuid", q: "dragon", sort: "-created_at", cursor: "tok" });
  });
});
