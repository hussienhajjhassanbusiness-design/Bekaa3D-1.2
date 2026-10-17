// #ARCHITECTURE-PRODUCT-WIRE-CONTRACT
//
// Raw wire shapes for the catalogue endpoints, transcribed field-for-field
// from docs/backend-handoff/openapi.json (components.schemas.ProductListItem/
// ProductDetail/ProductPage/PublicImage/PriceRead/CategorySummary/
// FacetSummary/Capabilities/DimensionsRead/ProductType/PurchaseMode) — this
// is a CONFIRMED, built contract (BACKEND-RESPONSE.md B2/B3), not a
// placeholder. Every field name/nullability below is a direct quote; nothing
// here is invented (bekaa3d-api-contract).
//
// Kept snake_case and otherwise untouched from the wire shape on purpose —
// camelCase, UI-facing models live in productAdapters.ts, built by explicit
// adapter functions. No component anywhere imports these wire types
// directly.

export type ProductType = "physical" | "stl";

export type PurchaseMode = "online_only" | "whatsapp_only" | "both";

export interface PriceRead {
  amount_cents: number;
  currency: string;
}

export interface PublicImage {
  id: string;
  url: string;
  alt_text: string | null;
  is_cover: boolean;
}

export interface CategorySummary {
  id: string;
  name: string;
  slug: string;
}

export interface FacetSummary {
  id: string;
  name: string;
}

export interface DimensionsRead {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface Capabilities {
  can_add_to_cart: boolean;
  can_offer: boolean;
  whatsapp_available: boolean;
}

export interface ProductListItem {
  id: string;
  type: ProductType;
  name: string;
  slug: string;
  cover_image: PublicImage | null;
  price: PriceRead;
  category: CategorySummary;
  material: FacetSummary | null;
  colour: FacetSummary | null;
  is_available: boolean;
  purchase_mode: PurchaseMode | null;
  average_rating: number;
  review_count: number;
  is_featured: boolean;
}

export interface ProductDetail extends ProductListItem {
  description: string | null;
  images: readonly PublicImage[];
  seo_title: string | null;
  seo_description: string | null;
  og_image_url: string | null;
  dimensions: DimensionsRead | null;
  production_lead_time_days: number | null;
  batch_size: number | null;
  max_quantity_per_line: number | null;
  capabilities: Capabilities;
}

export interface ProductPage {
  items: readonly ProductListItem[];
  next_cursor: string | null;
}

// GET /api/v1/products query parameters — openapi.json's own parameter
// list for paths./api/v1/products.get. `sort`'s enum is the server's full
// allowlist (B2): never add a value here that isn't one of these five.
export type ProductSort = "price" | "-price" | "-average_rating" | "-created_at" | "-relevance";

export interface ProductsQueryParams {
  type?: ProductType;
  category_id?: string;
  material_id?: string;
  colour_id?: string;
  price_min_cents?: number;
  price_max_cents?: number;
  min_rating?: number;
  featured?: boolean;
  q?: string;
  sort?: ProductSort;
  cursor?: string;
  limit?: number;
}
