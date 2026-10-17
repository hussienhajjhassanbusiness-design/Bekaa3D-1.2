import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { AdminUserDetail, AdminUserPage, AdminUsersQueryParams } from "./customerTypes";

// P1-4 — direct quotes of the confirmed query parameter names
// (docs/backend-handoff/BACKEND-RESPONSE.md). Omit a parameter entirely
// when unset, same convention as the storefront's own
// buildProductsSearchParams.
function buildUsersSearchParams(params: AdminUsersQueryParams): URLSearchParams {
  const search = new URLSearchParams();
  if (params.verified !== undefined) search.set("verified", String(params.verified));
  if (params.active !== undefined) search.set("active", String(params.active));
  if (params.search) search.set("search", params.search);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  return search;
}

async function listUsers(params: AdminUsersQueryParams): Promise<AdminUserPage> {
  const search = buildUsersSearchParams(params).toString();
  const path = search ? `/api/v1/admin/users?${search}` : "/api/v1/admin/users";
  return adminRequest(() => apiClient.get<AdminUserPage>(path));
}

async function getUser(userId: string): Promise<AdminUserDetail> {
  return adminRequest(() => apiClient.get<AdminUserDetail>(`/api/v1/admin/users/${encodeURIComponent(userId)}`));
}

// Only `is_active` is ever writable (AGENTS.md) — the request type takes
// just that, never email/role/password, matching the backend's own
// `additionalProperties: false` AdminUserUpdate schema.
async function updateUserActive(userId: string, isActive: boolean): Promise<AdminUserDetail> {
  return adminRequest(() =>
    apiClient.patch<AdminUserDetail>(
      `/api/v1/admin/users/${encodeURIComponent(userId)}`,
      { is_active: isActive },
      { csrf: true }
    )
  );
}

export const customersApi = { listUsers, getUser, updateUserActive };

export const customersKeys = {
  root: ["admin", "customers"] as const,
  list: (params: AdminUsersQueryParams) => [...customersKeys.root, "list", params] as const,
  detail: (userId: string) => [...customersKeys.root, "detail", userId] as const,
};
