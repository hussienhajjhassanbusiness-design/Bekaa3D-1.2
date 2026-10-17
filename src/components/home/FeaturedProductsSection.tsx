"use client";

import { useProducts } from "@/lib/catalog/useProducts";
import { toProductCardModel } from "@/lib/catalog/productAdapters";
import { ProductGrid } from "@/components/catalog/ProductGrid";

const FEATURED_PRODUCTS_LIMIT = 8;

// #FVS022-FEATURED-PRODUCTS-SECTION
//
// Reuses FVS-013's own ProductGrid/ProductCard (plan's own instruction:
// "reusing ProductCard/ProductGrid from FVS-013") — no second product-card
// implementation. `featured: true` is a real, confirmed query parameter
// (B2); if no product is marked featured, the grid's own real empty state
// renders (no invented "coming soon" placeholder) — so the section is
// simply omitted by the caller when there's nothing to show, rather than
// ever faking a product list.
export function FeaturedProductsSection() {
  const featuredQuery = useProducts({ featured: true, limit: FEATURED_PRODUCTS_LIMIT });
  const cardModels = (featuredQuery.data?.pages ?? []).flatMap((page) => page.items).map(toProductCardModel);

  // Shows the loading skeleton (FVS-022's own required UX state) while
  // pending, but once settled, the whole section is omitted on EITHER a
  // fetch failure or genuinely zero featured products — the home page
  // never shows a broken/error section for an optional extra, matching
  // CategoryShowcaseSection's own same rule and this phase's "omit rather
  // than show a placeholder" instruction. /shop's own grid still shows a
  // real, retryable error state for the primary catalogue experience.
  if (!featuredQuery.isLoading && (featuredQuery.isError || cardModels.length === 0)) {
    return null;
  }

  return (
    <section aria-labelledby="featured-products-heading" className="mt-12">
      <h2 id="featured-products-heading" className="text-h2 font-bold text-text-primary">
        Featured Products
      </h2>
      <div className="mt-4">
        <ProductGrid products={cardModels} isLoading={featuredQuery.isLoading} isError={featuredQuery.isError} />
      </div>
    </section>
  );
}
