"use client";

import Link from "next/link";
import { useProducts } from "@/lib/catalog/useProducts";
import { toProductCardModel } from "@/lib/catalog/productAdapters";
import { ProductGrid } from "@/components/catalog/ProductGrid";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { SectionHeader } from "@/components/ui/SectionHeader";

const FEATURED_PRODUCTS_LIMIT = 8;

// #FVS022-FEATURED-PRODUCTS-SECTION
//
// Reuses FVS-013's own ProductGrid/ProductCard (plan's own instruction:
// "reusing ProductCard/ProductGrid from FVS-013") — no second product-card
// implementation. `featured: true` is a real, confirmed query parameter
// (B2); if no product is marked featured, the section is omitted rather
// than ever faking a product list.
//
// Batch 3 — Stitch "Physical Masterpieces" (PAGE-SPECS S1 §3): split
// section header with a "View all products" link to the real /shop, and
// the showcase grid (4-up from 1280px).
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
    <section aria-labelledby="featured-products-heading" className="py-section-mobile tablet:py-section">
      <Container>
        <SectionHeader
          headingId="featured-products-heading"
          title="Featured Products"
          description="Hand-picked prints and files from the catalogue."
          align="split"
          action={
            <Link
              href="/shop"
              className="group inline-flex min-h-11 items-center gap-2 rounded-control font-label text-label-caps uppercase text-primary hover:text-primary-container"
            >
              View all products
              <Icon
                name="arrow-forward"
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
              />
            </Link>
          }
        />
        <ProductGrid products={cardModels} isLoading={featuredQuery.isLoading} isError={featuredQuery.isError} layout="showcase" />
      </Container>
    </section>
  );
}
