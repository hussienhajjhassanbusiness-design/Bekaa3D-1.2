"use client";

import { Suspense } from "react";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { ShopView } from "@/components/catalog/ShopView";

// FVS-013 — `/shop`. useSearchParams() opts the page out of static
// prerendering unless wrapped in Suspense (Next.js App Router
// requirement, matching src/app/login/page.tsx's own precedent) — the
// fallback is never visible in practice since the value is available
// synchronously on the client.
export default function ShopPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ShopView />
    </Suspense>
  );
}
