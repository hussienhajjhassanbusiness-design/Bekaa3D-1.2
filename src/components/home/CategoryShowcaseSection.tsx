"use client";

import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { useCategories } from "@/lib/catalog/useReferenceData";

// #FVS022-CATEGORY-SHOWCASE
//
// Real categories only, from the same confirmed `GET /api/v1/categories`
// FVS-013's FilterPanel uses (B2) — never a hardcoded category list. If
// the fetch fails or returns nothing, the section is simply omitted
// rather than showing a broken/empty shelf.
//
// Batch 3 — Stitch "Curated Specialized Collections" bento (COMPONENT-SPECS
// §13): one large feature tile plus a tile per category. Categories carry
// no images, so the tiles are tonal (route doc), never stock photos. The
// large tile is the real "whole catalogue" destination (/shop); each
// category tile links to /shop?category=<id>, exactly as before.
export function CategoryShowcaseSection() {
  const categoriesQuery = useCategories();
  const categories = categoriesQuery.data ?? [];

  if (categoriesQuery.isLoading || categoriesQuery.isError || categories.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="categories-heading" className="bg-surface-container-lowest py-section-mobile tablet:py-section">
      <Container>
        <SectionHeader
          headingId="categories-heading"
          title="Shop by Category"
          description="Physical prints and STL files, organised the way you look for them."
        />
        <ul className="grid grid-cols-1 gap-gutter sm:grid-cols-2 lg:grid-cols-4">
          <li className="sm:col-span-2 lg:row-span-2">
            <Link
              href="/shop"
              className="group relative flex h-full min-h-60 flex-col justify-end overflow-hidden rounded-panel bg-primary-container p-8 text-on-primary shadow-sm"
            >
              <span aria-hidden="true" className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
              <span className="relative mb-3 font-label text-label-caps uppercase tracking-widest text-on-primary-container">Full catalogue</span>
              <span className="relative mb-3 font-headline text-headline-lg">Shop all products</span>
              <span className="relative mb-6 max-w-sm font-body text-body-md text-on-primary">
                Every physical print and STL file in one place.
              </span>
              <span className="relative inline-flex items-center gap-2 font-label text-label-caps uppercase">
                Browse the shop
                <Icon
                  name="arrow-forward"
                  className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
                />
              </span>
            </Link>
          </li>
          {categories.map((category) => (
            <li key={category.id}>
              <Link
                href={`/shop?category=${category.id}`}
                className="group flex h-full min-h-36 flex-col justify-between rounded-panel sm:min-h-48 lg:min-h-60 border border-outline-variant/30 bg-surface-container-low p-6 transition-colors duration-200 hover:border-primary/30 hover:bg-surface-container"
              >
                <span
                  aria-hidden="true"
                  className="flex h-12 w-12 items-center justify-center rounded-card bg-surface-container-lowest text-primary shadow-sm"
                >
                  <Icon name="category" />
                </span>
                <span className="flex items-end justify-between gap-4">
                  <span className="font-headline text-headline-md text-on-surface">{category.name}</span>
                  <Icon
                    name="arrow-forward"
                    className="h-5 w-5 text-primary transition-transform duration-200 group-hover:translate-x-1 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
