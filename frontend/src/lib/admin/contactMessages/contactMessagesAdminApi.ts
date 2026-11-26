import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { ContactMessageStatus } from "@/lib/admin/contactMessageWorkflow";

// #FVS-CONTACT-QUEUE (phase 6B-1) — /api/v1/admin/contact-messages (backend
// 2dfb27b engagement/api/contact_messages.py; VS-033). Admin boundary: a
// non-admin gets 404, no session / MFA incomplete is 401.
//   GET   ?cursor&limit(1-100, default 20)&status&created_after&created_before&email
//         -> {items: ContactMessageDetail[], next_cursor}. Queue order: new
//         first, then oldest first. created_* must carry a UTC offset
//         (inclusive / exclusive); email is exact and case-insensitive.
//         Audited server-side (PII).
//   GET   /{id} -> ContactMessageDetail. Reading does NOT mark it read.
//   PATCH /{id} {status} CSRF -> ContactMessageDetail. Forward only, skips
//         allowed; backwards is 409 INVALID_STATE_TRANSITION. The reply
//         itself happens outside the system (by email).
// A customer's "Report a problem" on an order lands here too, with
// user_id and order_id set.

export interface ContactMessageDTO {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  subject: string | null;
  message: string;
  status: ContactMessageStatus;
  created_at: string;
  updated_at: string;
  user_id: string | null;
  order_id: string | null;
}

export interface ContactMessagePageDTO {
  items: ContactMessageDTO[];
  next_cursor: string | null;
}

export interface ContactMessagesQueryParams {
  status?: ContactMessageStatus;
  created_after?: string;
  created_before?: string;
  email?: string;
  cursor?: string;
  limit?: number;
}

const BASE = "/api/v1/admin/contact-messages";

function listMessages(params: ContactMessagesQueryParams): Promise<ContactMessagePageDTO> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.created_after) search.set("created_after", params.created_after);
  if (params.created_before) search.set("created_before", params.created_before);
  if (params.email) search.set("email", params.email);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const q = search.toString();
  return adminRequest(() => apiClient.get<ContactMessagePageDTO>(q ? `${BASE}?${q}` : BASE));
}

function getMessage(id: string): Promise<ContactMessageDTO> {
  return adminRequest(() => apiClient.get<ContactMessageDTO>(`${BASE}/${encodeURIComponent(id)}`));
}

function updateStatus(id: string, status: ContactMessageStatus): Promise<ContactMessageDTO> {
  return adminRequest(() => apiClient.patch<ContactMessageDTO>(`${BASE}/${encodeURIComponent(id)}`, { status }, { csrf: true }));
}

export const contactMessagesAdminApi = { listMessages, getMessage, updateStatus };

// Under the user-scoped ["admin"] root (cleared on sign-out / user switch).
export const contactMessageKeys = {
  root: ["admin", "contact-messages"] as const,
  list: (params: ContactMessagesQueryParams) => [...contactMessageKeys.root, "list", params] as const,
  detail: (id: string) => [...contactMessageKeys.root, "detail", id] as const,
};
