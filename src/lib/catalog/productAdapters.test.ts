import { describe, it, expect } from "vitest";
import { toProductCardModel, toProductDetailModel } from "./productAdapters";
import type { ProductDetail, ProductListItem } from "./productTypes";

// REAL STOREFRONT INTEGRATION — PHASE 1. Adapter tests written before/with
// the adapter (TDD) against the CONFIRMED wire contract transcribed in
// productTypes.ts (docs/backend-handoff/openapi.json — ProductListItem/
// ProductDetail; BACKEND-RESPONSE.md B2/B3 real captured examples). These
// fixtures mirror the backend's own real examples (dragon / dragon-stl)
// field-for-field — never an invented field.

const physicalListItem: ProductListItem = {
  id: "bfe73498-21a9-4bc2-bda6-44fdd8a90962",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  cover_image: {
    id: "e8fbdad8-af60-4a33-8772-77b1d96360aa",
    url: "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
    alt_text: "Articulated Dragon, view 1",
    is_cover: true,
  },
  price: { amount_cents: 1800, currency: "USD" },
  list_price: { amount_cents: 1800, currency: "USD" },
  promotion: null,
  category: { id: "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3", name: "Toys and Figures", slug: "toys-figures" },
  material: { id: "86f2d315-41be-491d-8a3e-09a599237ffe", name: "PLA" },
  colour: { id: "7aeecf3f-50a6-488b-b0e1-3739df5b2ae3", name: "Red" },
  is_available: true,
  purchase_mode: "both",
  average_rating: 0,
  review_count: 0,
  is_featured: false,
};

const stlListItem: ProductListItem = {
  id: "d2350ee4-c868-4fbe-a85e-ca3bb3109b42",
  type: "stl",
  name: "Articulated Dragon STL",
  slug: "dragon-stl",
  cover_image: {
    id: "151c3b59-75ae-4034-bd15-c5924a318bb5",
    url: "/media/products/ee1ed304-51a3-43d1-a57a-a0660b3c74a4.png",
    alt_text: "Articulated Dragon STL, view 1",
    is_cover: true,
  },
  price: { amount_cents: 700, currency: "USD" },
  list_price: { amount_cents: 700, currency: "USD" },
  promotion: null,
  category: { id: "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3", name: "Toys and Figures", slug: "toys-figures" },
  material: null,
  colour: null,
  is_available: true,
  purchase_mode: null,
  average_rating: 0,
  review_count: 0,
  is_featured: false,
};

describe("toProductCardModel", () => {
  it("maps every ProductListItem field onto the card model", () => {
    const model = toProductCardModel(physicalListItem);
    expect(model).toEqual({
      id: "bfe73498-21a9-4bc2-bda6-44fdd8a90962",
      type: "physical",
      name: "Articulated Dragon",
      slug: "dragon",
      coverImage: {
        src: "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
        alt: "Articulated Dragon, view 1",
      },
      price: { amountCents: 1800, currency: "USD" },
      promotion: null,
      category: { id: "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3", name: "Toys and Figures", slug: "toys-figures" },
      material: { id: "86f2d315-41be-491d-8a3e-09a599237ffe", name: "PLA" },
      colour: { id: "7aeecf3f-50a6-488b-b0e1-3739df5b2ae3", name: "Red" },
      isAvailable: true,
      purchaseMode: "both",
      averageRating: 0,
      reviewCount: 0,
      isFeatured: false,
    });
  });

  it("maps an active promotion with the server's own list price, never computing a price", () => {
    const item: ProductListItem = {
      ...physicalListItem,
      price: { amount_cents: 1440, currency: "USD" },
      list_price: { amount_cents: 1800, currency: "USD" },
      promotion: {
        id: "promo-1",
        name: "Eid Sale",
        badge_text: "Eid",
        discount_type: "percentage",
        discount_value: 20,
        ends_at: "2026-12-20T00:00:00Z",
      },
    };
    const model = toProductCardModel(item);
    expect(model.price).toEqual({ amountCents: 1440, currency: "USD" });
    expect(model.promotion).toEqual({
      id: "promo-1",
      name: "Eid Sale",
      badgeText: "Eid",
      discountType: "percentage",
      discountValue: 20,
      endsAt: "2026-12-20T00:00:00Z",
      listPrice: { amountCents: 1800, currency: "USD" },
    });
  });

  it("uses the server price as-is: a promotion's value is never applied to it", () => {
    const item: ProductListItem = {
      ...physicalListItem,
      // Deliberately inconsistent: the card must show the server's price,
      // not 1800 - 50%.
      price: { amount_cents: 1700, currency: "USD" },
      list_price: { amount_cents: 1800, currency: "USD" },
      promotion: {
        id: "promo-1",
        name: "Odd",
        badge_text: null,
        discount_type: "percentage",
        discount_value: 50,
        ends_at: "2026-12-20T00:00:00Z",
      },
    };
    expect(toProductCardModel(item).price.amountCents).toBe(1700);
  });

  it("falls back coverImage.alt to the product name when alt_text is null", () => {
    const item: ProductListItem = {
      ...physicalListItem,
      cover_image: { ...physicalListItem.cover_image!, alt_text: null },
    };
    expect(toProductCardModel(item).coverImage?.alt).toBe("Articulated Dragon");
  });

  it("maps a null cover_image to a null coverImage — never a fabricated placeholder image", () => {
    const item: ProductListItem = { ...physicalListItem, cover_image: null };
    expect(toProductCardModel(item).coverImage).toBeNull();
  });

  it("maps STL material/colour/purchase_mode null fields through as null, never defaulted", () => {
    const model = toProductCardModel(stlListItem);
    expect(model.material).toBeNull();
    expect(model.colour).toBeNull();
    expect(model.purchaseMode).toBeNull();
    expect(model.type).toBe("stl");
  });

  it("maps is_available: false through unchanged — this adapter never infers availability", () => {
    const model = toProductCardModel({ ...physicalListItem, is_available: false });
    expect(model.isAvailable).toBe(false);
  });
});

describe("toProductDetailModel", () => {
  const physicalDetail: ProductDetail = {
    ...physicalListItem,
    description: "Articulated Dragon: seeded by scripts/dev_seed.py for local testing.",
    images: [
      physicalListItem.cover_image!,
      {
        id: "93c25d4d-eae7-4c8b-9cc0-07dfcb9d1a1c",
        url: "/media/products/65cac7df-4e3b-4e8e-ac66-4453af11e561.png",
        alt_text: "Articulated Dragon, view 2",
        is_cover: false,
      },
    ],
    seo_title: null,
    seo_description: null,
    og_image_url: null,
    dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
    production_lead_time_days: 2,
    batch_size: 2,
    max_quantity_per_line: 5,
    capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: true },
  };

  const stlDetail: ProductDetail = {
    ...stlListItem,
    description: "Articulated Dragon STL: seeded by scripts/dev_seed.py for local testing.",
    images: [stlListItem.cover_image!],
    seo_title: null,
    seo_description: null,
    og_image_url: null,
    dimensions: null,
    production_lead_time_days: null,
    batch_size: null,
    max_quantity_per_line: null,
    capabilities: { can_add_to_cart: true, can_offer: true, whatsapp_available: false },
  };

  it("maps a physical product's full detail, including dimensions and capabilities", () => {
    const model = toProductDetailModel(physicalDetail);
    expect(model.description).toBe("Articulated Dragon: seeded by scripts/dev_seed.py for local testing.");
    expect(model.images).toHaveLength(2);
    expect(model.images[0]).toEqual({ id: physicalListItem.cover_image!.id, src: physicalListItem.cover_image!.url, alt: "Articulated Dragon, view 1" });
    expect(model.dimensions).toEqual({ lengthMm: 120, widthMm: 80, heightMm: 60 });
    expect(model.productionLeadTimeDays).toBe(2);
    expect(model.batchSize).toBe(2);
    expect(model.maxQuantityPerLine).toBe(5);
    expect(model.capabilities).toEqual({ canAddToCart: true, canOffer: false, whatsappAvailable: true });
  });

  it("maps an STL product's null physical-only fields through as null — never a placeholder label", () => {
    const model = toProductDetailModel(stlDetail);
    expect(model.dimensions).toBeNull();
    expect(model.productionLeadTimeDays).toBeNull();
    expect(model.batchSize).toBeNull();
    expect(model.maxQuantityPerLine).toBeNull();
    expect(model.material).toBeNull();
    expect(model.colour).toBeNull();
    expect(model.purchaseMode).toBeNull();
    expect(model.capabilities).toEqual({ canAddToCart: true, canOffer: true, whatsappAvailable: false });
  });

  it("maps a null description through as null", () => {
    const model = toProductDetailModel({ ...physicalDetail, description: null });
    expect(model.description).toBeNull();
  });

  it("falls back each gallery image's alt to the product name when alt_text is null", () => {
    const model = toProductDetailModel({
      ...physicalDetail,
      images: [{ ...physicalDetail.images[0]!, alt_text: null }],
    });
    expect(model.images[0]!.alt).toBe("Articulated Dragon");
  });
});
