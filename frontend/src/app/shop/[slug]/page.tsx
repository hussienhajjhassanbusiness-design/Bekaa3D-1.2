"use client";

import { useParams } from "next/navigation";
import { ProductDetailView } from "@/components/catalog/ProductDetailView";

// FVS-014 — `/shop/:slug`. Entirely client-rendered, matching this app's
// established data-fetching architecture (every other data page uses
// TanStack Query client-side; apiClient is a same-origin browser fetch,
// never usable from a Server Component). `useParams()` reads the already-
// resolved dynamic segment without the async `params` promise's extra
// Suspense plumbing, which this simple client page doesn't need.
export default function ShopProductPage() {
  const params = useParams<{ slug: string }>();
  return <ProductDetailView slug={params.slug} />;
}
