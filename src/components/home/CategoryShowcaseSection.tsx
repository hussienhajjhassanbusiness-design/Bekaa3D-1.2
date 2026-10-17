"use client";

import Link from "next/link";
import { useCategories } from "@/lib/catalog/useReferenceData";

// #FVS022-CATEGORY-SHOWCASE
//
// Real categories only, from the same confirmed `GET /api/v1/categories`
// FVS-013's FilterPanel uses (B2) — never a hardcoded category list. If
// the fetch fails or returns nothing, the section is simply omitted
// rather than showing a broken/empty shelf.
export function CategoryShowcaseSection() {
  const categoriesQuery = useCategories();
  const categories = categoriesQuery.data ?? [];

  if (categoriesQuery.isLoading || categoriesQuery.isError || categories.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="categories-heading" className="mt-12">
      <h2 id="categories-heading" className="text-h2 font-bold text-text-primary">
        Shop by Category
      </h2>
      <ul className="mt-4 flex flex-wrap gap-3">
        {categories.map((category) => (
          <li key={category.id}>
            <Link
              href={`/shop?category=${category.id}`}
              className="inline-block rounded-pill border border-border-default px-4 py-2 text-body text-text-primary hover:border-brand-dark-green hover:text-brand-dark-green"
            >
              {category.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
