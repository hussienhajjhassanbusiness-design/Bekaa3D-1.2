"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FilterPanel, type AppliedFilter, type FacetGroup } from "./FilterPanel";
import { SearchBar } from "./SearchBar";
import { SortSelect, type SortOption } from "./SortSelect";
import { ProductGrid } from "./ProductGrid";
import { DialogShell } from "@/components/feedback/DialogShell";
import { LoadMore } from "@/components/feedback/LoadMore";
import { Button } from "@/components/forms/Button";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { useSheetBehavior } from "@/components/ui/useSheetBehavior";
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

// The filter aside appears from the `desktop` breakpoint; below it, the drawer.
const DESKTOP_QUERY = "(min-width: 1024px)";

export function ShopView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const urlState = parseShopUrlState(searchParams);
  const [searchInput, setSearchInput] = useState(urlState.q);
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const filtersCloseRef = useRef<HTMLButtonElement>(null);
  const closeFilters = useCallback(() => setIsFiltersOpen(false), []);
  // Scroll lock while the drawer is open; it closes itself when the aside
  // takes over at 1024px.
  useSheetBehavior({ open: isFiltersOpen, onClose: closeFilters, closeAtQuery: DESKTOP_QUERY });
  // Focus moves into the drawer; DialogShell returns it to the trigger.
  useEffect(() => {
    if (isFiltersOpen) filtersCloseRef.current?.focus();
  }, [isFiltersOpen]);

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

  const filterPanel = (
    <FilterPanel
      groups={facetGroups}
      onChange={(groupId, value, checked) => handleFacetChange(groupId as FacetKey, value, checked)}
      appliedFilters={appliedFilters}
      onRemoveFilter={(groupId, value) => handleFacetChange(groupId as FacetKey, value, false)}
      onClearAll={appliedFilters.length > 0 ? handleClearAll : undefined}
    />
  );

  const isResultsSettled = !productsQuery.isLoading && !productsQuery.isError;

  return (
    <div className="pb-section-mobile tablet:pb-section">
      <Container className="pt-8 tablet:pt-12">
        {/* Stitch S2 image banner with search (COMPONENT-SPECS §9) without a
            stock photo: the dark inverse surface with a faint blueprint grid
            and a primary glow stands in for the darkened image. */}
        <section
          aria-labelledby="shop-heading"
          className="relative isolate overflow-hidden rounded-card bg-inverse-surface px-4 py-12 text-center tablet:px-12 tablet:py-16"
        >
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
            <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(255_255_255/0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/0.04)_1px,transparent_1px)] bg-[size:40px_40px]" />
            <div className="absolute -top-40 left-1/2 h-80 w-full max-w-xl -translate-x-1/2 rounded-full bg-primary/50 blur-3xl" />
          </div>
          <span className="mb-3 block font-label text-label-caps uppercase tracking-widest text-primary-fixed">
            Physical prints · STL files
          </span>
          <h1 id="shop-heading" className="font-display text-display text-inverse-on-surface">
            Shop
          </h1>
          <p className="mx-auto mt-3 max-w-xl font-body text-body-lg text-inverse-on-surface">
            Search the catalogue, or filter by category, material and colour.
          </p>
          <div className="mx-auto mt-8 max-w-2xl text-left">
            <SearchBar
              hideLabel
              value={searchInput}
              onChange={setSearchInput}
              onSubmit={(value) => updateUrl({ q: value })}
              suggestions={suggestionItems}
              isLoadingSuggestions={suggestions.isQueryLongEnough && suggestions.isLoading}
              onSelectSuggestion={(suggestion) => suggestion.href && router.push(suggestion.href)}
            />
          </div>
        </section>

        <div className="mt-10 flex flex-col gap-gutter desktop:mt-12 desktop:flex-row">
          {/* From 1024px the filters are a 256px aside; below that the same
              FilterPanel lives in the drawer, so cards keep a usable width. */}
          <aside aria-labelledby="shop-filters-heading" className="hidden desktop:block desktop:w-sidebar desktop:shrink-0">
            <h2 id="shop-filters-heading" className="mb-6 flex items-center gap-2 font-headline text-headline-md text-on-surface">
              <Icon name="filter-list" className="h-5 w-5" />
              Filters
            </h2>
            {filterPanel}
          </aside>

          <div className="min-w-0 flex-1">
            {/* Batch 11: names the results so the product cards' h3s sit
                under an h2 at every width (below 1024 the Filters h2 is in
                the closed drawer, which left an h1 → h3 skip). */}
            <h2 className="sr-only">Products</h2>
            {/* Stitch results toolbar (COMPONENT-SPECS §20). */}
            <div className="mb-8 flex flex-wrap items-center justify-between gap-4 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-sm">
              <div className="flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  onClick={() => setIsFiltersOpen(true)}
                  aria-haspopup="dialog"
                  aria-expanded={isFiltersOpen}
                  aria-controls="shop-filters-drawer"
                  aria-label={appliedFilters.length > 0 ? `Filters, ${appliedFilters.length} active` : "Filters"}
                  className="inline-flex min-h-11 items-center gap-2 rounded-control border-2 border-outline-variant bg-surface-container-lowest px-4 font-label text-label-caps uppercase text-on-surface transition-colors duration-200 hover:border-outline hover:bg-surface-container-high desktop:hidden"
                >
                  <Icon name="filter-list" className="h-5 w-5" />
                  Filters
                  {appliedFilters.length > 0 && (
                    <span
                      aria-hidden="true"
                      className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 font-body text-label-micro font-bold text-on-primary"
                    >
                      {appliedFilters.length}
                    </span>
                  )}
                </button>
                {/* Cursor paging has no total, so this counts what is shown. */}
                <p role="status" className="font-body text-body-md text-on-surface-variant">
                  {isResultsSettled && (
                    <>
                      <span className="font-bold text-on-surface">{cardModels.length}</span>{" "}
                      {cardModels.length === 1 ? "product" : "products"} shown
                      {productsQuery.hasNextPage ? ", more available" : ""}
                    </>
                  )}
                </p>
              </div>
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
      </Container>

      {/* Below 1024px: the same FilterPanel in a left sheet on the shared
          DialogShell (focus trap, Escape, backdrop, focus return). Filters
          apply as they are ticked, exactly as in the aside: the URL stays
          the only state, so opening or closing the drawer resets nothing. */}
      <DialogShell
        open={isFiltersOpen}
        onClose={closeFilters}
        labelledBy="shop-filters-drawer-title"
        panelClassName="fixed inset-y-0 left-0 flex h-dvh w-full max-w-sm flex-col border-r border-outline-variant/30 bg-surface shadow-2xl"
      >
        <div id="shop-filters-drawer" className="flex min-h-0 flex-1 flex-col">
          <div className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-outline-variant/30 px-margin-mobile">
            <h2 id="shop-filters-drawer-title" className="flex items-center gap-2 font-headline text-headline-md text-on-surface">
              <Icon name="filter-list" className="h-5 w-5" />
              Filters
            </h2>
            <button
              ref={filtersCloseRef}
              type="button"
              onClick={closeFilters}
              aria-label="Close filters"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors duration-200 hover:bg-surface-container hover:text-primary"
            >
              <Icon name="close" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-margin-mobile py-6">{filterPanel}</div>
          <div className="shrink-0 border-t border-outline-variant/30 p-margin-mobile">
            <Button type="button" size="lg" onClick={closeFilters} className="w-full">
              Show results
            </Button>
          </div>
        </div>
      </DialogShell>
    </div>
  );
}
