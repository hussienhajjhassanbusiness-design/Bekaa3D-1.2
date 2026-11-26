import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import type { PublicPromotionList } from "./promotionTypes";

// GET /api/v1/promotions — public, rate limited: the promotions active now,
// soonest ending first, with no product lists (the covered products are
// GET /api/v1/products?promotion_id=, priced by the server).
function listActivePromotions(): Promise<PublicPromotionList> {
  return apiClient.get<PublicPromotionList>("/api/v1/promotions");
}

export const promotionsApi = { listActivePromotions };

export const promotionKeys = {
  root: ["promotions"] as const,
  active: () => [...promotionKeys.root, "active"] as const,
};

export function useActivePromotions() {
  return useQuery({
    queryKey: promotionKeys.active(),
    queryFn: promotionsApi.listActivePromotions,
    // A campaign starting or ending should show up without a hard reload.
    staleTime: 60_000,
  });
}
