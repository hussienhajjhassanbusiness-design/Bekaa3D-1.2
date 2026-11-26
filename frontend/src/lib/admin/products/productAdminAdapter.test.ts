import { describe, it, expect } from "vitest";
import {
  toFormValues,
  toCreateBody,
  toUpdateBody,
  toGalleryImages,
  isValidSlugFormat,
  isPhysicalRequiredFieldsComplete,
  describeProductError,
} from "./productAdminAdapter";
import { EMPTY_PRODUCT_FORM_VALUES, type ProductFormValues, type RawAdminProductDetail } from "./productAdminTypes";

function rawProduct(overrides: Partial<RawAdminProductDetail>): RawAdminProductDetail {
  return {
    id: "p1",
    type: "physical",
    category_id: "cat1",
    name: "Moon Lamp",
    slug: "moon-lamp",
    price: { amount_cents: 1800, currency: "USD" },
    description: null,
    seo_title: null,
    seo_description: null,
    og_image_url: null,
    is_visible: true,
    is_featured: false,
    is_available: true,
    material_id: "mat1",
    colour_id: "col1",
    dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
    weight_grams: 200,
    production_lead_time_days: 2,
    batch_size: 2,
    max_quantity_per_line: 5,
    purchase_mode: "both",
    version: 3,
    average_rating: 0,
    review_count: 0,
    wishlist_count: 0,
    deleted_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    images: [],
    ...overrides,
  };
}

describe("toFormValues", () => {
  it("maps a physical product's fields", () => {
    const result = toFormValues(rawProduct({}));
    expect(result).toMatchObject({
      type: "physical",
      categoryId: "cat1",
      name: "Moon Lamp",
      slug: "moon-lamp",
      priceCents: 1800,
      materialId: "mat1",
      colourId: "col1",
      purchaseMode: "both",
      productionLeadTimeDays: 2,
      batchSize: 2,
      maxQuantityPerLine: 5,
      weightGrams: 200,
      lengthMm: 120,
      widthMm: 80,
      heightMm: 60,
    });
  });

  it("maps null physical-only fields to empty string ids / null numbers for an STL product", () => {
    const result = toFormValues(
      rawProduct({
        type: "stl",
        material_id: null,
        colour_id: null,
        dimensions: null,
        weight_grams: null,
        production_lead_time_days: null,
        batch_size: null,
        max_quantity_per_line: null,
        purchase_mode: null,
      })
    );
    expect(result).toMatchObject({
      type: "stl",
      materialId: "",
      colourId: "",
      lengthMm: null,
      widthMm: null,
      heightMm: null,
      weightGrams: null,
      productionLeadTimeDays: null,
    });
  });
});

describe("toCreateBody / toUpdateBody", () => {
  const physicalForm: ProductFormValues = {
    ...EMPTY_PRODUCT_FORM_VALUES,
    type: "physical",
    categoryId: "cat1",
    name: "Moon Lamp",
    slug: "moon-lamp",
    priceCents: 1800,
    productionLeadTimeDays: 2,
    batchSize: 2,
    maxQuantityPerLine: 5,
    lengthMm: 120,
    widthMm: 80,
    heightMm: 60,
  };

  it("includes type and physical-only fields for a physical create", () => {
    const body = toCreateBody(physicalForm);
    expect(body).toMatchObject({
      type: "physical",
      price: { amount_cents: 1800, currency: "USD" },
      purchase_mode: "online_only",
      production_lead_time_days: 2,
      batch_size: 2,
      max_quantity_per_line: 5,
      dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
    });
  });

  it("never includes any physical-only field for an STL create", () => {
    const body = toCreateBody({ ...physicalForm, type: "stl" });
    expect(body).not.toHaveProperty("purchase_mode");
    expect(body).not.toHaveProperty("production_lead_time_days");
    expect(body).not.toHaveProperty("batch_size");
    expect(body).not.toHaveProperty("max_quantity_per_line");
    expect(body).not.toHaveProperty("material_id");
    expect(body).not.toHaveProperty("colour_id");
    expect(body).not.toHaveProperty("dimensions");
    expect(body).not.toHaveProperty("weight_grams");
  });

  it("never includes a type field on an update (immutable)", () => {
    const body = toUpdateBody(physicalForm, 3);
    expect(body).not.toHaveProperty("type");
    expect(body).toMatchObject({ version: 3 });
  });

  it("sends cents as a whole integer, never a float conversion artifact", () => {
    const body = toCreateBody({ ...physicalForm, priceCents: 1099 });
    expect((body.price as { amount_cents: number }).amount_cents).toBe(1099);
    expect(Number.isInteger((body.price as { amount_cents: number }).amount_cents)).toBe(true);
  });

  it("converts empty optional text fields to null rather than empty strings", () => {
    const body = toCreateBody({ ...physicalForm, description: "", seoTitle: "", ogImageUrl: "" });
    expect(body.description).toBeNull();
    expect(body.seo_title).toBeNull();
    expect(body.og_image_url).toBeNull();
  });
});

describe("isValidSlugFormat", () => {
  it.each(["moon-lamp", "a", "a1-b2", "abc"])("accepts %s", (slug) => {
    expect(isValidSlugFormat(slug)).toBe(true);
  });

  it.each(["Moon Lamp", "moon_lamp", "moon--lamp", "-moon", "moon-", "", "MOON"])("rejects %s", (slug) => {
    expect(isValidSlugFormat(slug)).toBe(false);
  });
});

describe("isPhysicalRequiredFieldsComplete", () => {
  it("is always true for an STL product regardless of physical fields", () => {
    expect(isPhysicalRequiredFieldsComplete({ ...EMPTY_PRODUCT_FORM_VALUES, type: "stl" })).toBe(true);
  });

  it("is false for a physical product missing production lead time", () => {
    expect(
      isPhysicalRequiredFieldsComplete({ ...EMPTY_PRODUCT_FORM_VALUES, type: "physical", batchSize: 2, maxQuantityPerLine: 5 })
    ).toBe(false);
  });

  it("is true for a physical product with all three required numbers set", () => {
    expect(
      isPhysicalRequiredFieldsComplete({
        ...EMPTY_PRODUCT_FORM_VALUES,
        type: "physical",
        productionLeadTimeDays: 2,
        batchSize: 2,
        maxQuantityPerLine: 5,
      })
    ).toBe(true);
  });
});

describe("toGalleryImages", () => {
  it("sorts by sort_order and falls back to the product name when alt_text is null", () => {
    const result = toGalleryImages(
      [
        { id: "i2", product_id: "p1", url: "/media/b.png", alt_text: null, sort_order: 1, is_cover: false, created_at: "x", updated_at: "x" },
        { id: "i1", product_id: "p1", url: "/media/a.png", alt_text: "Front view", sort_order: 0, is_cover: true, created_at: "x", updated_at: "x" },
      ],
      "Moon Lamp"
    );
    expect(result.map((image) => image.id)).toEqual(["i1", "i2"]);
    expect(result[1]!.accessibleLabel).toBe("Moon Lamp");
    expect(result[0]!.isCover).toBe(true);
  });

  it("keeps the real alt text separate from the display fallback", () => {
    const result = toGalleryImages(
      [{ id: "i1", product_id: "p1", url: "/a.png", alt_text: null, sort_order: 0, is_cover: true, created_at: "x", updated_at: "x" }],
      "Moon Lamp"
    );
    expect(result[0]!.accessibleLabel).toBe("Moon Lamp");
    expect(result[0]!.altText).toBe("");
  });
});

describe("describeProductError", () => {
  it("flags VERSION_CONFLICT distinctly, with a safe re-fetch message", () => {
    const result = describeProductError({ kind: "http", status: 409, code: "VERSION_CONFLICT", message: "x", raw: undefined });
    expect(result.isVersionConflict).toBe(true);
    expect(result.bannerMessage).toMatch(/changed by someone else/i);
  });

  it("maps SLUG_CONFLICT to the slug field", () => {
    const result = describeProductError({ kind: "http", status: 409, code: "SLUG_CONFLICT", message: "x", raw: undefined });
    expect(result.fieldErrors).toEqual({ slug: "That slug is already in use by another live product." });
  });

  it("maps a VALIDATION_ERROR naming a known field onto that form field", () => {
    const result = describeProductError({
      kind: "http",
      status: 422,
      code: "VALIDATION_ERROR",
      message: "x",
      raw: undefined,
      errors: [{ loc: ["body", "batch_size"], msg: "x", type: "value_error" }],
    });
    expect(result.fieldErrors).toEqual({ batchSize: "Enter a valid value for this field." });
  });

  it("falls back to a generic banner for an unmapped error", () => {
    const result = describeProductError({ kind: "network", message: "x", raw: undefined });
    expect(result.bannerMessage).toBeTruthy();
    expect(result.fieldErrors).toBeUndefined();
  });
});
