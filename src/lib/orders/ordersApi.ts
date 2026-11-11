import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { OrderDetailReadDTO, OrderPageDTO } from "./orderTypes";

// #ARCHITECTURE-CUSTOMER-ORDERS-API
//
// GET /api/v1/me/orders?cursor&limit (also status, placed_after,
// placed_before — not used by phase 5E's UI) and GET
// /api/v1/me/orders/{order_id}. Both are session-authenticated reads (no
// CSRF); authenticatedRequest gives them the one refresh-then-retry-once
// behaviour on 401 AUTH_REQUIRED that every authenticated call shares.
export interface ListMyOrdersParams {
  cursor?: string;
  limit?: number;
}

export function buildOrdersSearchParams(params: ListMyOrdersParams): URLSearchParams {
  const search = new URLSearchParams();
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  return search;
}

async function listMyOrders(params: ListMyOrdersParams = {}): Promise<OrderPageDTO> {
  const search = buildOrdersSearchParams(params).toString();
  const path = search ? `/api/v1/me/orders?${search}` : "/api/v1/me/orders";
  return authenticatedRequest(() => apiClient.get<OrderPageDTO>(path));
}

async function getMyOrder(orderId: string): Promise<OrderDetailReadDTO> {
  return authenticatedRequest(() =>
    apiClient.get<OrderDetailReadDTO>(`/api/v1/me/orders/${encodeURIComponent(orderId)}`)
  );
}

export const ordersApi = { listMyOrders, getMyOrder };
