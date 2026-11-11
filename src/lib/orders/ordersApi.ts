import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type {
  OrderDetailReadDTO,
  OrderPageDTO,
  PaymentRetryReadDTO,
  PaymentRetryRequestDTO,
  ProblemReportCreateDTO,
} from "./orderTypes";

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

// FVS-027 (phase 5F) — POST /api/v1/me/orders/{order_id}/payments: a new
// payment attempt for the caller's own unpaid online order. CSRF and the
// required Idempotency-Key (paymentRetryIdempotency.ts). The key and the
// fixed `{}` body are captured once in this closure, so the shared
// refresh-on-401-then-retry-once wrapper can only resend the identical
// request, which the server treats as the same retry. Like checkout, the
// server calls the provider between two transactions, so the client waits
// longer than its default before calling the outcome unknown.
export const PAYMENT_RETRY_TIMEOUT_MS = 30_000;

async function retryPayment(orderId: string, idempotencyKey: string): Promise<PaymentRetryReadDTO> {
  const body: PaymentRetryRequestDTO = {};
  return authenticatedRequest(() =>
    apiClient.post<PaymentRetryReadDTO>(`/api/v1/me/orders/${encodeURIComponent(orderId)}/payments`, body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
      timeoutMs: PAYMENT_RETRY_TIMEOUT_MS,
    })
  );
}

// FVS-031 (phase 5G) — the customer's three order actions (backend 2dfb27b
// ordering/api/cancel.py, ordering/api/receipt.py). Each: verified session,
// CSRF, and the answer is the full OrderDetailRead, which the caller
// writes into the canonical orderKeys.detail(id) cache. None is idempotency-
// keyed; the shared refresh-on-401-then-retry-once wrapper resends the
// identical request only after the session was refreshed (a 401 is
// answered before the route body runs, so nothing changed).
//
// cancel: the optional `{ reason? (<=500) }` body is not collected by the
// UI (it is an audit note only), so no body is sent.
function actionPath(orderId: string, action: "cancel" | "confirm-receipt" | "report-problem"): string {
  return `/api/v1/me/orders/${encodeURIComponent(orderId)}/${action}`;
}

async function cancelOrder(orderId: string): Promise<OrderDetailReadDTO> {
  return authenticatedRequest(() =>
    apiClient.post<OrderDetailReadDTO>(actionPath(orderId, "cancel"), undefined, { csrf: true })
  );
}

async function confirmReceipt(orderId: string): Promise<OrderDetailReadDTO> {
  return authenticatedRequest(() =>
    apiClient.post<OrderDetailReadDTO>(actionPath(orderId, "confirm-receipt"), undefined, { csrf: true })
  );
}

async function reportProblem(orderId: string, message: string): Promise<OrderDetailReadDTO> {
  const body: ProblemReportCreateDTO = { message };
  return authenticatedRequest(() =>
    apiClient.post<OrderDetailReadDTO>(actionPath(orderId, "report-problem"), body, { csrf: true })
  );
}

export const ordersApi = { listMyOrders, getMyOrder, retryPayment, cancelOrder, confirmReceipt, reportProblem };
