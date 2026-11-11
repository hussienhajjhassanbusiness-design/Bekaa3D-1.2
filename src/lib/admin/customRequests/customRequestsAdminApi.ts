import { apiClient, type BinaryResponse } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { CustomRequestOutcome, CustomRequestStatus } from "./customRequestPipeline";

// #FVS-BYI-PIPELINE (phase 6B-2) — /api/v1/admin/custom-requests and the
// funnel (backend 2dfb27b engagement/api/custom_request_admin.py,
// admin_analytics.py; VS-035, ADR-031). Admin boundary: non-admin 404,
// no session / MFA incomplete 401. Reads showing PII are audited server-side.
//   GET  ?cursor&limit(1-100, 20)&status&created_after&created_before&email
//        -> {items: CustomRequestSummary[], next_cursor}; pipeline order
//        (new first, then oldest first; closed and lost last)
//   GET  /{id} -> CustomRequestDetail (only unexpired attachments)
//   PATCH /{id} {admin_notes: string|null <= 5000} CSRF; blank clears
//   POST /{id}/transition {target_status, quoted_amount_cents?} CSRF;
//        409 INVALID_STATE_TRANSITION, 422 for a missing/misplaced quote
//   GET  /{id}/attachments/{aid}/download -> the re-encoded image bytes,
//        Content-Disposition attachment; expired/missing 404
//   GET  /api/v1/admin/analytics/custom-requests/funnel?from&to -> one
//        cohort by submission date (from inclusive, to exclusive; default
//        the last 90 days; at most 366 days; aware datetimes)

export interface CustomRequestAttachmentDTO {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  expires_at: string;
  created_at: string;
}

export interface CustomRequestSummaryDTO {
  id: string;
  name: string;
  email: string;
  phone: string;
  project_title: string;
  status: CustomRequestStatus;
  quoted_amount_cents: number | null;
  currency: string | null;
  outcome: CustomRequestOutcome | null;
  attachment_count: number;
  created_at: string;
  updated_at: string;
}

export interface CustomRequestDetailDTO {
  id: string;
  name: string;
  email: string;
  phone: string;
  project_title: string;
  description: string;
  preferred_material: string | null;
  preferred_colour: string | null;
  dimensions: string | null;
  status: CustomRequestStatus;
  quoted_amount_cents: number | null;
  currency: string | null;
  outcome: CustomRequestOutcome | null;
  admin_notes: string | null;
  contacted_at: string | null;
  quoted_at: string | null;
  completed_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  attachments: CustomRequestAttachmentDTO[];
}

export interface CustomRequestPageDTO {
  items: CustomRequestSummaryDTO[];
  next_cursor: string | null;
}

export interface CustomRequestFunnelDTO {
  from: string;
  to: string;
  submitted: number;
  contacted: number;
  quoted: number;
  won: number;
  lost: number;
  open: number;
  quoted_total_cents: number;
  won_total_cents: number;
  currency: string;
}

export interface CustomRequestsQueryParams {
  status?: CustomRequestStatus;
  created_after?: string;
  created_before?: string;
  email?: string;
  cursor?: string;
  limit?: number;
}

export interface CustomRequestFunnelParams {
  from?: string;
  to?: string;
}

export interface CustomRequestTransitionDTO {
  target_status: CustomRequestStatus;
  quoted_amount_cents?: number;
}

const BASE = "/api/v1/admin/custom-requests";
const path = (id: string) => `${BASE}/${encodeURIComponent(id)}`;

function withQuery(base: string, entries: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(entries)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const q = search.toString();
  return q ? `${base}?${q}` : base;
}

function listRequests(params: CustomRequestsQueryParams): Promise<CustomRequestPageDTO> {
  const url = withQuery(BASE, {
    status: params.status,
    created_after: params.created_after,
    created_before: params.created_before,
    email: params.email,
    cursor: params.cursor,
    limit: params.limit,
  });
  return adminRequest(() => apiClient.get<CustomRequestPageDTO>(url));
}

function getRequest(id: string): Promise<CustomRequestDetailDTO> {
  return adminRequest(() => apiClient.get<CustomRequestDetailDTO>(path(id)));
}

function updateNotes(id: string, adminNotes: string | null): Promise<CustomRequestDetailDTO> {
  return adminRequest(() => apiClient.patch<CustomRequestDetailDTO>(path(id), { admin_notes: adminNotes }, { csrf: true }));
}

function transition(id: string, body: CustomRequestTransitionDTO): Promise<CustomRequestDetailDTO> {
  return adminRequest(() => apiClient.post<CustomRequestDetailDTO>(`${path(id)}/transition`, body, { csrf: true }));
}

function downloadAttachment(id: string, attachmentId: string): Promise<BinaryResponse> {
  return adminRequest(() =>
    apiClient.getBlob(`${path(id)}/attachments/${encodeURIComponent(attachmentId)}/download`, { timeoutMs: 60_000 })
  );
}

function getFunnel(params: CustomRequestFunnelParams): Promise<CustomRequestFunnelDTO> {
  return adminRequest(() =>
    apiClient.get<CustomRequestFunnelDTO>(withQuery("/api/v1/admin/analytics/custom-requests/funnel", { from: params.from, to: params.to }))
  );
}

export const customRequestsAdminApi = { listRequests, getRequest, updateNotes, transition, downloadAttachment, getFunnel };

// Under the user-scoped ["admin"] root (cleared on sign-out / user switch).
export const customRequestKeys = {
  root: ["admin", "custom-requests"] as const,
  list: (params: CustomRequestsQueryParams) => [...customRequestKeys.root, "list", params] as const,
  detail: (id: string) => [...customRequestKeys.root, "detail", id] as const,
  funnel: (params: CustomRequestFunnelParams) => [...customRequestKeys.root, "funnel", params] as const,
};
