import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { ProductCard } from "./ProductCard";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

export interface ProductGridProps {
  products: readonly ProductCardModel[];
  isLoading: boolean;
  isError: boolean;
  emptyMessage?: string;
  onClearFilters?: () => void;
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
}: ProductGridProps) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
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
    <ul className="grid grid-cols-1 gap-gutter tablet:grid-cols-2 desktop:grid-cols-3">
      {products.map((product) => (
        <li key={product.id}>
          <ProductCard product={product} />
        </li>
      ))}
    </ul>
  );
}
