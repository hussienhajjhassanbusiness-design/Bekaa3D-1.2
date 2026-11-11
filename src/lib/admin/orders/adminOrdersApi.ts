import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type {
  AdminOrderCancelRequestDTO,
  AdminOrderDetailDTO,
  AdminOrderPageDTO,
  AdminOrdersQueryParams,
  AdminOrderUpdateDTO,
  CashHandoverRequestDTO,
  OrderItemTransitionRequestDTO,
  StlDeliveriesQueryParams,
  StlDeliveryPageDTO,
} from "./adminOrderTypes";

// #FVS030-ADMIN-ORDERS-API (phase 5H)
//
// Every call goes through adminRequest (refresh-once on AUTH_REQUIRED, the
// MFA_REQUIRED signal). Writes send X-CSRF-Token. None is idempotency-
// keyed and none is retried by the caller: a state-changing conflict is a
// 409 the administrator reads, never a silent resend. Every write answers
// with the full AdminOrderDetail, which the caller writes into the
// canonical adminOrderKeys.detail(id).

export function buildAdminOrdersSearchParams(params: AdminOrdersQueryParams): URLSearchParams {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.fulfillment_method) search.set("fulfillment_method", params.fulfillment_method);
  if (params.payment_method) search.set("payment_method", params.payment_method);
  if (params.payment_due !== undefined) search.set("payment_due", String(params.payment_due));
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.order_number) search.set("order_number", params.order_number);
  if (params.placed_after) search.set("placed_after", params.placed_after);
  if (params.placed_before) search.set("placed_before", params.placed_before);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  return search;
}

const orderPath = (orderId: string) => `/api/v1/admin/orders/${encodeURIComponent(orderId)}`;

async function listOrders(params: AdminOrdersQueryParams): Promise<AdminOrderPageDTO> {
  const search = buildAdminOrdersSearchParams(params).toString();
  return adminRequest(() => apiClient.get<AdminOrderPageDTO>(search ? `/api/v1/admin/orders?${search}` : "/api/v1/admin/orders"));
}

async function getOrder(orderId: string): Promise<AdminOrderDetailDTO> {
  return adminRequest(() => apiClient.get<AdminOrderDetailDTO>(orderPath(orderId)));
}

async function transitionLine(
  orderId: string,
  itemId: string,
  body: OrderItemTransitionRequestDTO
): Promise<AdminOrderDetailDTO> {
  return adminRequest(() =>
    apiClient.post<AdminOrderDetailDTO>(`${orderPath(orderId)}/items/${encodeURIComponent(itemId)}/transition`, body, {
      csrf: true,
    })
  );
}

async function cashHandover(orderId: string, body: CashHandoverRequestDTO): Promise<AdminOrderDetailDTO> {
  return adminRequest(() => apiClient.post<AdminOrderDetailDTO>(`${orderPath(orderId)}/cash-handover`, body, { csrf: true }));
}

async function cancelOrder(orderId: string, body: AdminOrderCancelRequestDTO): Promise<AdminOrderDetailDTO> {
  return adminRequest(() => apiClient.post<AdminOrderDetailDTO>(`${orderPath(orderId)}/cancel`, body, { csrf: true }));
}

async function updateNote(orderId: string, body: AdminOrderUpdateDTO): Promise<AdminOrderDetailDTO> {
  return adminRequest(() => apiClient.patch<AdminOrderDetailDTO>(orderPath(orderId), body, { csrf: true }));
}

async function listStlDeliveries(params: StlDeliveriesQueryParams): Promise<StlDeliveryPageDTO> {
  const search = new URLSearchParams();
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const query = search.toString();
  return adminRequest(() =>
    apiClient.get<StlDeliveryPageDTO>(query ? `/api/v1/admin/stl-deliveries?${query}` : "/api/v1/admin/stl-deliveries")
  );
}

export const adminOrdersApi = { listOrders, getOrder, transitionLine, cashHandover, cancelOrder, updateNote, listStlDeliveries };

// The one admin order query-key family. Under the shared ["admin"] root,
// which is dropped with every other user-scoped cache on logout / user
// switch (userScopedQueries.ts).
export const adminOrderKeys = {
  root: ["admin", "orders"] as const,
  lists: () => [...adminOrderKeys.root, "list"] as const,
  list: (params: AdminOrdersQueryParams) => [...adminOrderKeys.lists(), params] as const,
  detail: (orderId: string) => [...adminOrderKeys.root, "detail", orderId] as const,
  stl: (params: StlDeliveriesQueryParams) => [...adminOrderKeys.root, "stl-deliveries", params] as const,
};
