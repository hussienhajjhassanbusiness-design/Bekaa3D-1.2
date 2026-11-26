import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";

// #FVS-CASH-BLOCKS (phase 6A) — /api/v1/admin/cash-blocks (backend 2dfb27b
// ordering/api/admin_cash_blocks.py; SRS 9.8.6, ADR-024 d6, ADR-038).
//
// A cash payment block is created AUTOMATICALLY when every live line of a
// cash order ends cancelled with reason `refused` or `no_show` (there is no
// manual "block" route). It keeps that customer and phone off cash
// checkout until an administrator clears it; it does not expire. It is not
// an account deactivation, a payment failure or an order cancellation.
//   GET  /admin/cash-blocks?customer_id&active&limit&cursor  newest first
//   POST /admin/cash-blocks/search {phone, active?, limit?, cursor?}  CSRF;
//        the phone travels in the body only (never a URL or log) and is
//        hashed server-side; 422 for a non-Lebanese number
//   POST /admin/cash-blocks/{id}/clear  CSRF; clearing a cleared block
//        changes nothing (returns it unchanged)
// Responses never include the phone or its hash. 60/h per admin on writes.

export interface CashPaymentBlockReadDTO {
  id: string;
  customer_id: string;
  order_id: string;
  order_number: string;
  reason: "refused" | "no_show" | "other";
  created_at: string;
  active: boolean;
  cleared_at: string | null;
  cleared_by: string | null;
}

export interface CashPaymentBlockPageDTO {
  items: CashPaymentBlockReadDTO[];
  next_cursor: string | null;
}

export interface CashBlocksQueryParams {
  customer_id?: string;
  active?: boolean;
  cursor?: string;
  limit?: number;
}

export interface CashBlockSearchDTO {
  phone: string; // <= 32, normalised server-side
  active?: boolean;
  cursor?: string;
  limit?: number;
}

async function listBlocks(params: CashBlocksQueryParams): Promise<CashPaymentBlockPageDTO> {
  const search = new URLSearchParams();
  if (params.customer_id) search.set("customer_id", params.customer_id);
  if (params.active !== undefined) search.set("active", String(params.active));
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const q = search.toString();
  return adminRequest(() => apiClient.get<CashPaymentBlockPageDTO>(q ? `/api/v1/admin/cash-blocks?${q}` : "/api/v1/admin/cash-blocks"));
}

async function searchBlocks(body: CashBlockSearchDTO): Promise<CashPaymentBlockPageDTO> {
  return adminRequest(() => apiClient.post<CashPaymentBlockPageDTO>("/api/v1/admin/cash-blocks/search", body, { csrf: true }));
}

async function clearBlock(blockId: string): Promise<CashPaymentBlockReadDTO> {
  return adminRequest(() =>
    apiClient.post<CashPaymentBlockReadDTO>(`/api/v1/admin/cash-blocks/${encodeURIComponent(blockId)}/clear`, undefined, { csrf: true })
  );
}

export const cashBlocksApi = { listBlocks, searchBlocks, clearBlock };

// Under the user-scoped ["admin"] root. The phone is never part of a key.
export const cashBlockKeys = {
  root: ["admin", "cash-blocks"] as const,
  list: (params: CashBlocksQueryParams) => [...cashBlockKeys.root, "list", params] as const,
};
