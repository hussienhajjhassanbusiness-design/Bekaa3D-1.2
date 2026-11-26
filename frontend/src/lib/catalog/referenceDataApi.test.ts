import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { referenceDataApi, referenceDataKeys } from "./referenceDataApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("referenceDataApi", () => {
  it("getCategories calls GET /api/v1/categories and unwraps items", async () => {
    const getSpy = vi
      .spyOn(apiClient, "get")
      .mockResolvedValue({ items: [{ id: "c1", name: "Toys", slug: "toys" }] });

    const categories = await referenceDataApi.getCategories();

    expect(getSpy).toHaveBeenCalledWith("/api/v1/categories");
    expect(categories).toEqual([{ id: "c1", name: "Toys", slug: "toys" }]);
  });

  it("getMaterials calls GET /api/v1/materials and unwraps items", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [{ id: "m1", name: "PLA" }] });

    const materials = await referenceDataApi.getMaterials();

    expect(getSpy).toHaveBeenCalledWith("/api/v1/materials");
    expect(materials).toEqual([{ id: "m1", name: "PLA" }]);
  });

  it("getColours calls GET /api/v1/colours and unwraps items", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [{ id: "co1", name: "Red" }] });

    const colours = await referenceDataApi.getColours();

    expect(getSpy).toHaveBeenCalledWith("/api/v1/colours");
    expect(colours).toEqual([{ id: "co1", name: "Red" }]);
  });
});

describe("referenceDataKeys", () => {
  it("gives each entity its own stable, distinct query key", () => {
    expect(referenceDataKeys.categories()).toEqual(["referenceData", "categories"]);
    expect(referenceDataKeys.materials()).toEqual(["referenceData", "materials"]);
    expect(referenceDataKeys.colours()).toEqual(["referenceData", "colours"]);
  });
});
