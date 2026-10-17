"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FilterPanel, type AppliedFilter, type FacetGroup } from "./FilterPanel";
import { SearchBar } from "./SearchBar";
import { SortSelect, type SortOption } from "./SortSelect";
import { ProductGrid } from "./ProductGrid";
import { LoadMore } from "@/components/feedback/LoadMore";
import { parseShopUrlState, buildShopUrlParams, type ShopUrlState } from "@/lib/catalog/shopUrlState";
import { toProductsQueryParams } from "@/lib/catalog/shopQueryAdapter";
import { useProducts } from "@/lib/catalog/useProducts";
import { useCategories, useMaterials, useColours } from "@/lib/catalog/useReferenceData";
import { toProductCardModel } from "@/lib/catalog/productAdapters";
import { useSearchSuggestions } from "@/lib/search/useSearchSuggestions";

// #FVS013-SHOP-VIEW
//
// URL state is the source of truth (FVS-013 §0's own "State" line) — every
// filter/sort/search/cursor change is a router.push, never local component
// state standing in for it, so the browser back/forward buttons and a
// shared link always reproduce the exact same view.
//
// Facet selection is single-value per group (B2: "one value per facet" —
// confirmed, not guessed) even though FilterPanel renders checkboxes:
// checking an option in a facet group REPLACES that facet's current
// selection rather than adding to it, and unchecking the selected option
// clears the facet. This is the UI-level enforcement of a contract rule,
// not a FilterPanel limitation.
const SORT_OPTIONS: readonly SortOption[] = [
  { value: "", label: "Newest" },
  { value: "-relevance", label: "Best match" },
  { value: "price", label: "Price: Low to High" },
  { value: "-price", label: "Price: High to Low" },
  { value: "-average_rating", label: "Highest Rated" },
];

type FacetKey = "category" | "material" | "colour";

export function ShopView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const urlState = parseShopUrlState(searchParams);
  const [searchInput, setSearchInput] = useState(urlState.q);
  const [isMobileFiltersOpen, setIsMobileFiltersOpen] = useState(false);

  // Keeps the search box in sync with the committed URL `q` after a
  // back/forward navigation or a filter-triggered URL change — never
  // fights the user's own in-progress typing, since this only reacts to
  // the committed value actually changing. Adjusted during render (React's
  // own "adjusting state when a prop changes" pattern), not inside a
  // useEffect, which would cause an extra commit/cascading render for a
  // value already known at render time.
  const [lastSyncedQ, setLastSyncedQ] = useState(urlState.q);
  if (urlState.q !== lastSyncedQ) {
    setLastSyncedQ(urlState.q);
    setSearchInput(urlState.q);
  }

  function updateUrl(updates: Partial<ShopUrlState>) {
    const next = buildShopUrlParams(searchParams, updates);
    router.push(`${pathname}?${next.toString()}`);
  }

  const categoriesQuery = useCategories();
  const materialsQuery = useMaterials();
  const coloursQuery = useColours();

  function handleFacetChange(facet: FacetKey, value: string, checked: boolean) {
    const isCurrentlySelected = urlState[facet][0] === value;
    if (checked) {
      updateUrl({ [facet]: [value] });
    } else if (isCurrentlySelected) {
      updateUrl({ [facet]: [] });
    }
  }

  const facetGroups: readonly FacetGroup[] = [
    {
      id: "category",
      legend: "Category",
      options: (categoriesQuery.data ?? []).map((category) => ({
        value: category.id,
        label: category.name,
        checked: urlState.category[0] === category.id,
      })),
    },
    {
      id: "material",
      legend: "Material",
      options: (materialsQuery.data ?? []).map((material) => ({
        value: material.id,
        label: material.name,
        checked: urlState.material[0] === material.id,
      })),
    },
    {
      id: "colour",
      legend: "Colour",
      options: (coloursQuery.data ?? []).map((colour) => ({
        value: colour.id,
        label: colour.name,
        checked: urlState.colour[0] === colour.id,
      })),
    },
  ];

  const appliedFilters: AppliedFilter[] = facetGroups.flatMap((group) =>
    group.options.filter((option) => option.checked).map((option) => ({
      groupId: group.id,
      value: option.value,
      label: option.label,
    }))
  );

  function handleClearAll() {
    updateUrl({ category: [], material: [], colour: [] });
  }

  const suggestions = useSearchSuggestions(searchInput);
  const suggestionItems = suggestions.isQueryLongEnough
    ? (suggestions.data ?? []).map((item) => ({ label: item.name, href: `/shop/${item.slug}` }))
    : undefined;

  const apiParams = useMemo(() => toProductsQueryParams(urlState), [urlState]);
  const productsQuery = useProducts(apiParams);

  const cardModels = useMemo(
    () => (productsQuery.data?.pages ?? []).flatMap((page) => page.items).map(toProductCardModel),
    [productsQuery.data]
  );

  async function handleLoadMore() {
    const result = await productsQuery.fetchNextPage();
    const pages = result.data?.pages ?? [];
    const lastPage = pages[pages.length - 1];
    if (lastPage) {
      // Stores the cursor for the NEXT page after the one just loaded —
      // reloading this URL resumes browsing forward from here rather than
      // replaying every previously-loaded page, which a single opaque
      // cursor cannot reconstruct (C2: cursors are not random-access).
      updateUrl({ cursor: lastPage.next_cursor });
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 tablet:px-6 desktop:px-8">
      <h1 className="text-h1 font-bold text-text-primary">Shop</h1>

      <div className="mt-4">
        <SearchBar
          value={searchInput}
          onChange={setSearchInput}
          onSubmit={(value) => updateUrl({ q: value })}
          suggestions={suggestionItems}
          isLoadingSuggestions={suggestions.isQueryLongEnough && suggestions.isLoading}
          onSelectSuggestion={(suggestion) => suggestion.href && router.push(suggestion.href)}
        />
      </div>

      <div className="mt-6 flex flex-col gap-6 tablet:flex-row">
        <button
          type="button"
          onClick={() => setIsMobileFiltersOpen((open) => !open)}
          aria-expanded={isMobileFiltersOpen}
          className="rounded-md border border-border-default px-4 py-2 text-body font-semibold text-text-primary tablet:hidden"
        >
          {isMobileFiltersOpen ? "Hide filters" : "Filters"}
        </button>

        <aside className={`${isMobileFiltersOpen ? "block" : "hidden"} tablet:block tablet:w-64 tablet:shrink-0`}>
          <FilterPanel
            groups={facetGroups}
            onChange={(groupId, value, checked) => handleFacetChange(groupId as FacetKey, value, checked)}
            appliedFilters={appliedFilters}
            onRemoveFilter={(groupId, value) => handleFacetChange(groupId as FacetKey, value, false)}
            onClearAll={appliedFilters.length > 0 ? handleClearAll : undefined}
          />
        </aside>

        <div className="flex-1">
          <div className="mb-4 flex justify-end">
            <SortSelect options={SORT_OPTIONS} value={urlState.sort ?? ""} onChange={(next) => updateUrl({ sort: next })} />
          </div>

          <ProductGrid
            products={cardModels}
            isLoading={productsQuery.isLoading}
            isError={productsQuery.isError}
            onClearFilters={appliedFilters.length > 0 ? handleClearAll : undefined}
          />

          <LoadMore
            hasMore={Boolean(productsQuery.hasNextPage)}
            onLoadMore={handleLoadMore}
            isLoading={productsQuery.isFetchingNextPage}
          />
        </div>
      </div>
    </div>
  );
}
