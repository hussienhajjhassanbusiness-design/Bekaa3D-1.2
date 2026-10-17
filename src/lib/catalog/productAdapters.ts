import type {
  Capabilities,
  CategorySummary,
  DimensionsRead,
  FacetSummary,
  ProductDetail,
  ProductListItem,
  ProductType,
  PublicImage,
  PurchaseMode,
} from "./productTypes";

// #ARCHITECTURE-PRODUCT-DISPLAY-MODEL
//
// UI-facing, camelCase models — the only shape ProductCard/ProductGrid/the
// product detail page ever see. Adapters below are the single place that
// converts the confirmed wire contract (productTypes.ts) into this shape;
// no component imports productTypes directly or re-implements this mapping
// (bekaa3d-api-contract: adapt in one place, never duplicate).
//
// Every null in the wire contract is preserved as null here — never
// defaulted to a placeholder string/zero/false, since (per B2/B3) null is a
// meaningful "this does not apply to this product type" signal, not missing
// data.
export interface ProductCardImage {
  src: string;
  alt: string;
}

export interface ProductCardModel {
  id: string;
  type: ProductType;
  name: string;
  slug: string;
  coverImage: ProductCardImage | null;
  price: { amountCents: number; currency: string };
  category: CategorySummary;
  material: FacetSummary | null;
  colour: FacetSummary | null;
  isAvailable: boolean;
  purchaseMode: PurchaseMode | null;
  averageRating: number;
  reviewCount: number;
  isFeatured: boolean;
}

export interface ProductGalleryImageModel {
  id: string;
  src: string;
  alt: string;
}

export interface ProductDimensionsModel {
  lengthMm: number;
  widthMm: number;
  heightMm: number;
}

export interface ProductCapabilitiesModel {
  canAddToCart: boolean;
  canOffer: boolean;
  whatsappAvailable: boolean;
}

export interface ProductDetailModel extends ProductCardModel {
  description: string | null;
  images: readonly ProductGalleryImageModel[];
  dimensions: ProductDimensionsModel | null;
  productionLeadTimeDays: number | null;
  batchSize: number | null;
  maxQuantityPerLine: number | null;
  capabilities: ProductCapabilitiesModel;
}

function toCoverImage(image: PublicImage | null, fallbackAlt: string): ProductCardImage | null {
  if (!image) {
    return null;
  }
  return { src: image.url, alt: image.alt_text ?? fallbackAlt };
}

function toDimensions(dimensions: DimensionsRead | null): ProductDimensionsModel | null {
  if (!dimensions) {
    return null;
  }
  return { lengthMm: dimensions.length_mm, widthMm: dimensions.width_mm, heightMm: dimensions.height_mm };
}

function toCapabilities(capabilities: Capabilities): ProductCapabilitiesModel {
  return {
    canAddToCart: capabilities.can_add_to_cart,
    canOffer: capabilities.can_offer,
    whatsappAvailable: capabilities.whatsapp_available,
  };
}

export function toProductCardModel(item: ProductListItem): ProductCardModel {
  return {
    id: item.id,
    type: item.type,
    name: item.name,
    slug: item.slug,
    coverImage: toCoverImage(item.cover_image, item.name),
    price: { amountCents: item.price.amount_cents, currency: item.price.currency },
    category: item.category,
    material: item.material,
    colour: item.colour,
    isAvailable: item.is_available,
    purchaseMode: item.purchase_mode,
    averageRating: item.average_rating,
    reviewCount: item.review_count,
    isFeatured: item.is_featured,
  };
}

export function toProductDetailModel(detail: ProductDetail): ProductDetailModel {
  return {
    ...toProductCardModel(detail),
    description: detail.description,
    images: detail.images.map((image) => ({
      id: image.id,
      src: image.url,
      alt: image.alt_text ?? detail.name,
    })),
    dimensions: toDimensions(detail.dimensions),
    productionLeadTimeDays: detail.production_lead_time_days,
    batchSize: detail.batch_size,
    maxQuantityPerLine: detail.max_quantity_per_line,
    capabilities: toCapabilities(detail.capabilities),
  };
}
