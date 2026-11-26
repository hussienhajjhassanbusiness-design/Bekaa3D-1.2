// #ARCHITECTURE-PROMOTION-WIRE-CONTRACT
//
// Seasonal promotions (Eid, Ramadan, Christmas…): administrator-created
// store/product price campaigns. Transcribed from the backend's
// docs/frontend-handoff/openapi.json (PublicPromotionRead, AdminPromotionRead,
// AdminPromotionCreate, AdminPromotionUpdate) and docs/promotions.md.
//
// Not an offer (one customer's negotiation) and not a coupon (nothing is
// redeemed). The server owns every price: the frontend formats these fields
// as labels and never computes a sell price from `discount_value`.
import type { DiscountType } from "@/lib/catalog/productTypes";

export type { DiscountType };

export type PromotionScope = "all" | "physical" | "stl" | "selected";

// Derived by the server from `active` and the window; never computed here.
export type PromotionStatus = "scheduled" | "active" | "ended" | "inactive";

export interface PublicPromotionRead {
  id: string;
  name: string;
  badge_text: string | null;
  discount_type: DiscountType;
  // A whole percent for `percentage`; cents (USD) for `fixed`.
  discount_value: number;
  scope: PromotionScope;
  starts_at: string;
  ends_at: string;
}

export interface PublicPromotionList {
  items: readonly PublicPromotionRead[];
}

export interface AdminPromotionRead extends PublicPromotionRead {
  product_ids: readonly string[];
  active: boolean;
  status: PromotionStatus;
  created_at: string;
  updated_at: string;
}

export interface AdminPromotionList {
  items: readonly AdminPromotionRead[];
}

export interface AdminPromotionWrite {
  name: string;
  badge_text: string | null;
  discount_type: DiscountType;
  discount_value: number;
  scope: PromotionScope;
  product_ids: string[];
  starts_at: string;
  ends_at: string;
  active: boolean;
}

// Backend limits (app/catalog/domain/promotions.py).
export const PROMOTION_NAME_MAX = 80;
export const PROMOTION_BADGE_MAX = 24;
export const PROMOTION_SELECTED_MAX = 200;
export const PROMOTION_CURRENCY = "USD";
