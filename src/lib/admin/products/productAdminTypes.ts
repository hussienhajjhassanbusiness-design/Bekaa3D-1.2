// P1-6 (docs/backend-handoff/BACKEND-RESPONSE.md, openapi.json
// `AdminProductCreate`/`AdminProductUpdate`/`AdminProductDetail`) — the
// confirmed admin product contract. Money is integer cents, USD only.
// Product type is fixed at creation and never sent on PATCH.
export type ProductType = "physical" | "stl";
export type PurchaseMode = "online_only" | "whatsapp_only" | "both";

export interface RawPrice {
  amount_cents: number;
  currency: string;
}

export interface RawDimensions {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface RawProductImage {
  id: string;
  product_id: string;
  url: string;
  alt_text: string | null;
  sort_order: number;
  is_cover: boolean;
  created_at: string;
  updated_at: string;
}

// Shared by AdminProductCreate (minus id/version/etc.) and
// AdminProductDetail (read side) — kept as one type since the response
// is a strict superset of the create fields.
export interface RawAdminProductDetail {
  id: string;
  type: ProductType;
  category_id: string;
  name: string;
  slug: string;
  price: RawPrice;
  description: string | null;
  seo_title: string | null;
  seo_description: string | null;
  og_image_url: string | null;
  is_visible: boolean;
  is_featured: boolean;
  is_available: boolean;
  material_id: string | null;
  colour_id: string | null;
  dimensions: RawDimensions | null;
  weight_grams: number | null;
  production_lead_time_days: number | null;
  batch_size: number | null;
  max_quantity_per_line: number | null;
  purchase_mode: PurchaseMode | null;
  version: number;
  average_rating: number;
  review_count: number;
  wishlist_count: number;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  images: RawProductImage[];
}

export interface RawAdminProductPage {
  items: RawAdminProductDetail[];
  next_cursor: string | null;
}

export interface AdminProductsQueryParams {
  type?: ProductType;
  category_id?: string;
  is_visible?: boolean;
  is_featured?: boolean;
  is_available?: boolean;
  deleted?: boolean;
  q?: string;
  sort?: "-created_at" | "price" | "-price";
  cursor?: string;
  limit?: number;
}

// The UI-facing form model ProductForm actually edits. Money is
// cents-safe (MoneyInput's own contract); every physical-only field is
// still present on an STL draft (so the form doesn't need two branching
// shapes) but the adapter never sends it to the backend for type "stl".
export interface ProductFormValues {
  type: ProductType;
  categoryId: string;
  name: string;
  slug: string;
  priceCents: number | null;
  description: string;
  seoTitle: string;
  seoDescription: string;
  ogImageUrl: string;
  isVisible: boolean;
  isFeatured: boolean;
  isAvailable: boolean;
  materialId: string;
  colourId: string;
  purchaseMode: PurchaseMode;
  productionLeadTimeDays: number | null;
  batchSize: number | null;
  maxQuantityPerLine: number | null;
  weightGrams: number | null;
  lengthMm: number | null;
  widthMm: number | null;
  heightMm: number | null;
}

export const EMPTY_PRODUCT_FORM_VALUES: ProductFormValues = {
  type: "physical",
  categoryId: "",
  name: "",
  slug: "",
  priceCents: null,
  description: "",
  seoTitle: "",
  seoDescription: "",
  ogImageUrl: "",
  isVisible: false,
  isFeatured: false,
  isAvailable: true,
  materialId: "",
  colourId: "",
  purchaseMode: "online_only",
  productionLeadTimeDays: null,
  batchSize: null,
  maxQuantityPerLine: null,
  weightGrams: null,
  lengthMm: null,
  widthMm: null,
  heightMm: null,
};
