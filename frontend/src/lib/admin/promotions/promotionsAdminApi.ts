import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { AdminPromotionList, AdminPromotionRead, AdminPromotionWrite } from "@/lib/promotions/promotionTypes";

// Backend app/catalog/api/promotions.py (docs/promotions.md). Admin boundary:
// a non-admin gets 404; writes carry X-CSRF-Token.
//   GET   /api/v1/admin/promotions          newest first, at most 200
//   POST  /api/v1/admin/promotions          CSRF; 201
//   GET   /api/v1/admin/promotions/{id}
//   PATCH /api/v1/admin/promotions/{id}     CSRF; partial; `active` switches it on/off
// There is no delete: switch a promotion off, or let it end.
const BASE = "/api/v1/admin/promotions";

function path(id: string): string {
  return `${BASE}/${encodeURIComponent(id)}`;
}

function listPromotions(): Promise<AdminPromotionList> {
  return adminRequest(() => apiClient.get<AdminPromotionList>(BASE));
}

function getPromotion(id: string): Promise<AdminPromotionRead> {
  return adminRequest(() => apiClient.get<AdminPromotionRead>(path(id)));
}

function createPromotion(body: AdminPromotionWrite): Promise<AdminPromotionRead> {
  return adminRequest(() => apiClient.post<AdminPromotionRead>(BASE, body, { csrf: true }));
}

function updatePromotion(id: string, body: Partial<AdminPromotionWrite>): Promise<AdminPromotionRead> {
  return adminRequest(() => apiClient.patch<AdminPromotionRead>(path(id), body, { csrf: true }));
}

export const promotionsAdminApi = { listPromotions, getPromotion, createPromotion, updatePromotion };

// Under the user-scoped ["admin"] root (cleared on sign-out / user switch).
export const adminPromotionKeys = {
  root: ["admin", "promotions"] as const,
  list: () => [...adminPromotionKeys.root, "list"] as const,
  detail: (id: string) => [...adminPromotionKeys.root, "detail", id] as const,
};
