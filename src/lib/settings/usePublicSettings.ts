import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { publicSettingsKeys } from "./publicSettingsKeys";
import { toPublicSettingsModel, type PublicSettingsRead } from "./publicSettingsModel";

// The one shared GET /api/v1/settings/public query — FloatingWhatsAppButton
// (global shell) and the product-detail WhatsApp CTA both call this same
// hook, so they share one cached fetch rather than each issuing their own
// request (#ARCHITECTURE-CANONICAL-PUBLIC-SETTINGS). Public settings change
// rarely (an admin action) — a 1-minute staleTime avoids refetching on
// every route change while still catching a same-session settings update
// reasonably soon.
const PUBLIC_SETTINGS_STALE_TIME_MS = 60_000;

export function usePublicSettings() {
  return useQuery({
    queryKey: publicSettingsKeys.current(),
    queryFn: async () => {
      const raw = await apiClient.get<PublicSettingsRead>("/api/v1/settings/public");
      return toPublicSettingsModel(raw);
    },
    staleTime: PUBLIC_SETTINGS_STALE_TIME_MS,
  });
}
