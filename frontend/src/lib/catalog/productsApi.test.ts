import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { buildProductsSearchParams, productsApi, productsKeys } from "./productsApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildProductsSearchParams", () => {
  it("builds an empty querystring for no params", () => {
    expect(buildProductsSearchParams({}).toString()).toBe("");
  });

  it("uses the confirmed wire names category_id/material_id/colour_id — never category/material/colour", () => {
    const search = buildProductsSearchParams({
      category_id: "cat-1",
      material_id: "mat-1",
      colour_id: "col-1",
    });
    expect(search.get("category_id")).toBe("cat-1");
    expect(search.get("material_id")).toBe("mat-1");
    expect(search.get("colour_id")).toBe("col-1");
    expect(search.has("category")).toBe(false);
  });

  it("includes exactly one value per facet — one_id per param, no repeated-param serialization", () => {
    const search = buildProductsSearchParams({ category_id: "cat-1" });
    expect(search.getAll("category_id")).toEqual(["cat-1"]);
  });

  it("passes type/sort/q/cursor/limit through unchanged", () => {
    const search = buildProductsSearchParams({
      type: "physical",
      sort: "-price",
      q: "dragon",
      cursor: "opaque-cursor",
      limit: 20,
    });
    expect(search.get("type")).toBe("physical");
    expect(search.get("sort")).toBe("-price");
    expect(search.get("q")).toBe("dragon");
    expect(search.get("cursor")).toBe("opaque-cursor");
    expect(search.get("limit")).toBe("20");
  });

  it("serializes featured/price_min_cents/price_max_cents/min_rating, including the falsy value 0", () => {
    const search = buildProductsSearchParams({ featured: true, price_min_cents: 0, min_rating: 0 });
    expect(search.get("featured")).toBe("true");
    expect(search.get("price_min_cents")).toBe("0");
    expect(search.get("min_rating")).toBe("0");
  });

  it("omits an empty-string q rather than sending a blank search param", () => {
    expect(buildProductsSearchParams({ q: "" }).has("q")).toBe(false);
  });
});

describe("productsApi.listProducts", () => {
  it("calls GET /api/v1/products with no querystring when params are empty", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });

    await productsApi.listProducts({});

    expect(getSpy).toHaveBeenCalledWith("/api/v1/products");
  });

  it("calls GET /api/v1/products?<querystring> when params are set", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });

    await productsApi.listProducts({ category_id: "cat-1", sort: "-price" });

    const [calledPath] = getSpy.mock.calls[0]!;
    expect(calledPath).toBe("/api/v1/products?category_id=cat-1&sort=-price");
  });

  it("returns the page's items and next_cursor unchanged", async () => {
    const page = { items: [{ id: "p1" }], next_cursor: "next-token" };
    vi.spyOn(apiClient, "get").mockResolvedValue(page);

    const result = await productsApi.listProducts({});

    expect(result).toBe(page);
  });
});

describe("productsApi.getProductBySlug", () => {
  it("calls GET /api/v1/products/{slug}, URI-encoded", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ id: "p1" });

    await productsApi.getProductBySlug("dragon");

    expect(getSpy).toHaveBeenCalledWith("/api/v1/products/dragon");
  });
});

describe("productsKeys", () => {
  it("gives distinct list keys for distinct param sets", () => {
    const keyA = productsKeys.list({ category_id: "a" });
    const keyB = productsKeys.list({ category_id: "b" });
    expect(keyA).not.toEqual(keyB);
  });

  it("gives a distinct detail key per slug", () => {
    expect(productsKeys.detail("dragon")).toEqual(["products", "detail", "dragon"]);
  });
});
