import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ProductCard } from "./ProductCard";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

// "catalog": beside the shop's 256px filter aside from 1024px — 1 → 2
// (640) → 3 (1280) columns. "showcase": full-width home rows — 1 → 2 (640)
// → 3 (1024) → 4 (1280). Cards never drop below ~270px; fewer, well-sized
// cards beat squeezed ones.
export type ProductGridLayout = "catalog" | "showcase";

const GRID_CLASSES: Record<ProductGridLayout, string> = {
  catalog: "grid grid-cols-1 gap-gutter sm:grid-cols-2 xl:grid-cols-3",
  showcase: "grid grid-cols-1 gap-gutter sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};

const SKELETON_COUNT: Record<ProductGridLayout, number> = { catalog: 6, showcase: 4 };

export interface ProductGridProps {
  products: readonly ProductCardModel[];
  isLoading: boolean;
  isError: boolean;
  emptyMessage?: string;
  onClearFilters?: () => void;
  layout?: ProductGridLayout;
}

// Card-shaped placeholder (COMPONENT-SPECS §50): same radius, border,
// square media and body rhythm as ProductCard, so nothing jumps when the
// real cards arrive. Pulse is off under reduced motion.
function ProductCardSkeleton() {
  return (
    <li className="overflow-hidden rounded-card border border-outline-variant/30 bg-surface-container-lowest shadow-sm">
      <div className="aspect-square animate-pulse bg-surface-container-low motion-reduce:animate-none" />
      <div className="flex flex-col gap-3 p-6">
        <div className="h-6 w-16 animate-pulse rounded-badge bg-surface-container motion-reduce:animate-none" />
        <div className="h-6 w-3/4 animate-pulse rounded-badge bg-surface-container motion-reduce:animate-none" />
        <div className="h-6 w-1/3 animate-pulse rounded-badge bg-surface-container motion-reduce:animate-none" />
        <div className="mt-3 h-11 animate-pulse rounded-control bg-surface-container motion-reduce:animate-none" />
      </div>
    </li>
  );
}

// #FVS013-PRODUCT-GRID
//
// Owns exactly the three non-happy-path states FVS-013 §0 requires
// (loading/empty/error) for the grid itself — pagination
// (LoadMore) and filter/sort/search controls are siblings the page
// composes separately, not this component's concern. Semantic `<ul>`
// (bekaa3d-brand-ui: "grid is a list semantically").
export function ProductGrid({
  products,
  isLoading,
  isError,
  emptyMessage = "No products match your filters.",
  onClearFilters,
  layout = "catalog",
}: ProductGridProps) {
  if (isLoading) {
    return (
      <div role="status" aria-busy="true">
        {/* The shared loading copy (LoadingSpinner), inside the section that
            names what is loading. */}
        <span className="sr-only">Loading…</span>
        <ul aria-hidden="true" className={GRID_CLASSES[layout]}>
          {Array.from({ length: SKELETON_COUNT[layout] }, (_, index) => (
            <ProductCardSkeleton key={index} />
          ))}
        </ul>
      </div>
    );
  }

  if (isError) {
    return <Alert variant="error" message="We couldn't load products. Please try again." />;
  }

  if (products.length === 0) {
    return <EmptyState message={emptyMessage} actionLabel={onClearFilters ? "Clear filters" : undefined} onAction={onClearFilters} />;
  }

  return (
    <ul className={GRID_CLASSES[layout]}>
      {products.map((product) => (
        <li key={product.id}>
          <ProductCard product={product} />
        </li>
      ))}
    </ul>
  );
}
