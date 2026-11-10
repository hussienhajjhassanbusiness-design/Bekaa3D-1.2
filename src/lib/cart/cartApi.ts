import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { CartItemAddDTO, CartReadDTO } from "./cartTypes";

// #ARCHITECTURE-CART-API
//
// Every built cart operation in the current contract (openapi.json;
// backend 2dfb27b src/app/ordering/api/cart.py, docs/cart.md):
//   GET    /api/v1/cart                         read (never creates a cart)
//   POST   /api/v1/cart/items                   add / merge -> 200 CartRead
//   PATCH  /api/v1/cart/items/{product_id}      absolute quantity -> 200 CartRead
//   DELETE /api/v1/cart/items/{product_id}      remove line -> 204
// GET needs a session (an unverified user may read). Every write needs a
// verified email (403 EMAIL_VERIFICATION_REQUIRED) and the double-submit
// CSRF header (403 CSRF_INVALID). There is NO clear-cart route; checkout
// clears the cart server-side. All calls share the single
// refresh-on-401-then-retry-once wrapper.
const BASE = "/api/v1/cart";

function linePath(productId: string): string {
  return `${BASE}/items/${encodeURIComponent(productId)}`;
}

function getCart(): Promise<CartReadDTO> {
  return authenticatedRequest(() => apiClient.get<CartReadDTO>(BASE));
}

function addItem(body: CartItemAddDTO): Promise<CartReadDTO> {
  return authenticatedRequest(() => apiClient.post<CartReadDTO>(`${BASE}/items`, body, { csrf: true }));
}

// Body is exactly CartItemQuantityUpdate `{quantity}` (absolute, >= 1).
function setItemQuantity(productId: string, quantity: number): Promise<CartReadDTO> {
  return authenticatedRequest(() => apiClient.patch<CartReadDTO>(linePath(productId), { quantity }, { csrf: true }));
}

function removeItem(productId: string): Promise<void> {
  return authenticatedRequest(() => apiClient.del<void>(linePath(productId), { csrf: true }));
}

export const cartApi = { getCart, addItem, setItemQuantity, removeItem };
