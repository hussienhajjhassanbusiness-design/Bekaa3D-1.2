import Link from "next/link";
import { PriceDisplay } from "./PriceDisplay";
import { ProductTypeBadge } from "./ProductTypeBadge";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

export interface ProductCardProps {
  product: ProductCardModel;
}

// #FVS013-PRODUCT-CARD
//
// Built against the CONFIRMED `ProductListItem` contract (B2) — every
// field below traces directly to productAdapters.ts's ProductCardModel,
// itself a 1:1 map of the real wire shape. Never shows: stock quantity
// (no such field exists — B3's own "No stock" note), an invented
// discount, or a star rating — `average_rating`/`review_count` are real
// fields but are unconditionally 0 for every product until reviews ship
// (VS-036, B2's own note), so rendering a permanent "☆☆☆☆☆ 0.0 (0)" on
// every card would look like a broken/fake widget rather than real data;
// omitted until review_count can ever be non-zero.
//
// The whole card is ONE link (bekaa3d-brand-ui: "primary link wraps the
// whole clickable card without nesting interactive elements") — no
// separate "View" button, no nested anchors.
export function ProductCard({ product }: ProductCardProps) {
  return (
    <Link
      href={`/shop/${product.slug}`}
      className="group flex h-full flex-col overflow-hidden rounded-md border border-border-default bg-surface-base transition-shadow hover:shadow-elevation-1"
    >
      <div className="relative aspect-square w-full overflow-hidden bg-surface-sunken">
        {product.coverImage ? (
          // Plain <img>: the real image host's remote-pattern allowlist
          // can't be configured yet (FRONTEND-VERTICAL-SLICE-PLAN.md §17
          // image-URL item; matches ProductImageGallery's own same-gap
          // decision).
          <img
            src={product.coverImage.src}
            alt={product.coverImage.alt}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-caption text-text-disabled">
            No image available
          </div>
        )}
        <div className="absolute left-2 top-2 flex gap-1.5">
          <ProductTypeBadge type={product.type} />
          {product.isFeatured && (
            <span className="inline-block rounded-pill bg-brand-dark-green px-2 py-0.5 text-caption font-semibold text-text-on-brand">
              Featured
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-1 p-3">
        <span className="text-caption uppercase tracking-label text-text-secondary">{product.category.name}</span>
        <h3 className="text-body-lg font-semibold text-text-primary">{product.name}</h3>
        <div className="mt-auto flex items-center justify-between pt-2">
          <PriceDisplay amountCents={product.price.amountCents} currency={product.price.currency} />
          {!product.isAvailable && (
            <span className="rounded-pill bg-warning-bg px-2 py-0.5 text-caption font-semibold text-warning">
              Unavailable
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
