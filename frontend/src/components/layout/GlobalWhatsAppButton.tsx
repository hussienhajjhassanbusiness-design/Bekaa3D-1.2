"use client";

import { FloatingWhatsAppButton } from "./FloatingWhatsAppButton";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { useAdminChrome } from "./useAdminChrome";

// #FVS022-FLOATING-WHATSAPP-GLOBAL
//
// Mounted once in the root layout so every public page gets the floating
// button from the same shared public-settings query
// (#ARCHITECTURE-CANONICAL-PUBLIC-SETTINGS) — FVS-014's product-page CTA
// reads the same cached query via usePublicSettings(), never a second
// fetch. If the query fails, `data` stays undefined and
// FloatingWhatsAppButton already renders nothing for a null number —
// never a hardcoded fallback.
export function GlobalWhatsAppButton() {
  const settingsQuery = usePublicSettings();
  // Storefront chrome: not shown inside the admin shell (Batch 9, D5).
  const adminChrome = useAdminChrome();
  if (adminChrome) return null;
  return <FloatingWhatsAppButton whatsappNumber={settingsQuery.data?.whatsappNumber ?? null} />;
}
