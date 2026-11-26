import type { ProductType } from "@/lib/catalog/productTypes";
import type { CartLineReadDTO, CartReadDTO, PurchaseRefusal } from "./cartTypes";

// #ARCHITECTURE-CART-ADAPTER
//
// The UI-facing cart shape and the one place that converts the wire
// contract (cartTypes.ts) into it. Every null in the contract stays null.
// Server flags (price_changed, over_cap, purchasable) are carried as-is,
// never recomputed client-side. There is no total: CartRead has none, and
// checkout recomputes it from live prices (backend docs/cart.md).

export interface CartPrice {
  amountCents: number;
  currency: string;
}

export interface CartLineImage {
  src: string;
  alt: string;
}

export interface CartLineModel {
  productId: string;
  productType: ProductType;
  name: string | null;
  slug: string | null;
  coverImage: CartLineImage | null;
  quantity: number;
  snapshotPrice: CartPrice;
  currentPrice: CartPrice | null;
  priceChanged: boolean;
  maxQuantity: number | null;
  overCap: boolean;
  purchasable: boolean;
  unpurchasableReason: PurchaseRefusal | null;
}

export interface CartModel {
  id: string | null;
  lines: readonly CartLineModel[];
  containsPhysical: boolean;
  containsDigital: boolean;
  updatedAt: string | null;
}

// Display fallback for the (never in V1) null product name.
export const UNNAMED_PRODUCT = "Product no longer available";

export function adaptCartLine(dto: CartLineReadDTO): CartLineModel {
  return {
    productId: dto.product_id,
    productType: dto.product_type,
    name: dto.name,
    slug: dto.slug,
    coverImage: dto.cover_image
      ? { src: dto.cover_image.url, alt: dto.cover_image.alt_text ?? dto.name ?? UNNAMED_PRODUCT }
      : null,
    quantity: dto.quantity,
    snapshotPrice: { amountCents: dto.snapshot_price.amount_cents, currency: dto.snapshot_price.currency },
    currentPrice: dto.current_price
      ? { amountCents: dto.current_price.amount_cents, currency: dto.current_price.currency }
      : null,
    priceChanged: dto.price_changed,
    maxQuantity: dto.max_quantity,
    overCap: dto.over_cap,
    purchasable: dto.purchasable,
    unpurchasableReason: dto.unpurchasable_reason,
  };
}

export function adaptCart(dto: CartReadDTO): CartModel {
  return {
    id: dto.id,
    lines: dto.items.map(adaptCartLine),
    containsPhysical: dto.contains_physical,
    containsDigital: dto.contains_digital,
    updatedAt: dto.updated_at,
  };
}

// A count of units for the header indicator — never a monetary figure.
export function cartItemCount(cart: CartModel): number {
  return cart.lines.reduce((sum, line) => sum + line.quantity, 0);
}
