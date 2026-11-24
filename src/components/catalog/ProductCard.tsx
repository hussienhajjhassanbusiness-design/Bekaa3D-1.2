import Link from "next/link";
import { ProductPrice } from "./ProductPrice";
import { ProductTypeBadge } from "./ProductTypeBadge";
import { RatingSummary } from "./RatingSummary";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";
import { discountBadge } from "@/lib/promotions/promotionFormat";
import { Icon } from "@/components/ui/Icon";
import { WishlistButton } from "@/components/wishlist/WishlistButton";

export interface ProductCardProps {
  product: ProductCardModel;
}

// #FVS013-PRODUCT-CARD
//
// Built against the CONFIRMED `ProductListItem` contract (B2) — every
// field below traces directly to productAdapters.ts's ProductCardModel,
// itself a 1:1 map of the real wire shape. Never shows: stock quantity
// (no such field exists — B3's own "No stock" note) or an invented
// discount. The rating row renders only when `review_count` is above zero
// (it is 0 for every product until reviews ship, VS-036): a permanent
// "☆☆☆☆☆ (0)" on every card would look like a broken/fake widget.
//
// The whole card is ONE link (bekaa3d-brand-ui: "primary link wraps the
// whole clickable card without nesting interactive elements") — the
// "View details" call to action is part of that link, not a second
// control, and there are no nested anchors.
//
// Phase 6D: the wishlist heart is a SIBLING of the card link, positioned
// over the image corner, so the card stays one link with nothing
// interactive nested inside it.
//
// Batch 2 — Stitch catalog card (COMPONENT-SPECS §11b, recommended
// canonical): white surface, 12px radius, outline-variant/30 border,
// shadow-sm; square image on the lavender container with a slow zoom;
// category pill over the image; 24px body; Hanken 20px title; card price
// role; full-width solid primary CTA. Hover lifts the card 4px with a
// stronger shadow — on the wrapper, so the heart moves with it — and every
// transform is off under prefers-reduced-motion.
export function ProductCard({ product }: ProductCardProps) {
  return (
    <div className="group relative h-full transition-transform duration-300 ease-standard hover:-translate-y-1 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <Link
        href={`/shop/${product.slug}`}
        className="flex h-full flex-col overflow-hidden rounded-card border border-outline-variant/30 bg-surface-container-lowest shadow-sm transition-shadow duration-300 ease-standard group-hover:shadow-xl"
      >
        <div className="relative aspect-square w-full overflow-hidden bg-surface-container-low">
          {product.coverImage ? (
            // Plain <img>: the real image host's remote-pattern allowlist
            // can't be configured yet (FRONTEND-VERTICAL-SLICE-PLAN.md §17
            // image-URL item; matches ProductImageGallery's own same-gap
            // decision). object-cover in a fixed square: never tiled.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={product.coverImage.src}
              alt={product.coverImage.alt}
              className="h-full w-full object-cover transition-transform duration-500 ease-standard group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-on-surface-variant">
              <Icon name="image" className="h-10 w-10 text-outline" />
              <span className="font-label text-label-caps uppercase">No image available</span>
            </div>
          )}
          {/* Leaves the top-right corner to the wishlist heart. */}
          <div className="absolute left-4 top-4 flex max-w-[calc(100%-5.5rem)] flex-col items-start gap-1.5">
            <span className="max-w-full truncate rounded-full bg-primary px-3 py-1 font-label text-label-micro font-bold uppercase tracking-widest text-on-primary">
              {product.category.name}
            </span>
            {product.promotion && (
              // Stitch S1 card 2's "-30%" corner badge (tertiary), from the
              // server's own promotion; the sr text names the campaign.
              <span className="rounded-badge bg-tertiary px-2 py-1 font-label text-label-micro font-bold uppercase text-on-tertiary">
                {discountBadge(
                  product.promotion.discountType,
                  product.promotion.discountValue,
                  product.promotion.listPrice.currency
                )}
                <span className="sr-only"> {product.promotion.name}</span>
              </span>
            )}
            {product.isFeatured && (
              <span className="rounded-badge bg-on-surface-variant px-2 py-1 font-label text-label-micro font-bold uppercase text-on-primary">
                Featured
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-1 flex-col p-6">
          <div className="mb-3 flex min-h-6 flex-wrap items-center justify-between gap-2">
            <ProductTypeBadge type={product.type} />
            <RatingSummary averageRating={product.averageRating} reviewCount={product.reviewCount} />
          </div>
          <h3 className="line-clamp-2 font-headline text-headline-md text-on-surface transition-colors duration-200 group-hover:text-primary">
            {product.name}
          </h3>
          <div className="mb-6 mt-2 flex flex-wrap items-center justify-between gap-2">
            <ProductPrice price={product.price} promotion={product.promotion} size="card" />
            {!product.isAvailable && (
              <span className="rounded-full bg-warning-container px-3 py-1 font-label text-label-sm font-bold uppercase text-on-warning-container">
                Unavailable
              </span>
            )}
          </div>
          <span className="mt-auto flex min-h-11 w-full items-center justify-center gap-2 rounded-control bg-primary px-4 font-label text-label-caps uppercase text-on-primary transition-colors duration-200 group-hover:bg-primary-container">
            View details
            <Icon name="arrow-forward" className="h-4 w-4" />
          </span>
        </div>
      </Link>
      <div className="absolute right-4 top-4">
        <WishlistButton
          productId={product.id}
          productName={product.name}
          returnToPath={`/shop/${product.slug}`}
          variant="icon"
        />
      </div>
    </div>
  );
}
