"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { useProduct } from "@/lib/catalog/useProduct";
import { toProductDetailModel } from "@/lib/catalog/productAdapters";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { MakeOfferPanel } from "@/components/offers/MakeOfferPanel";
import { WishlistButton } from "@/components/wishlist/WishlistButton";
import { AddToCartButton } from "./AddToCartButton";
import { PriceDisplay } from "./PriceDisplay";
import { ProductImageGallery } from "./ProductImageGallery";
import { ProductTypeBadge } from "./ProductTypeBadge";
import { RatingSummary } from "./RatingSummary";
import { UnavailableNotice } from "./UnavailableNotice";
import { WhatsAppChatButton } from "./WhatsAppChatButton";

export interface ProductDetailViewProps {
  slug: string;
}

// Stitch spec tile (COMPONENT-SPECS §25): mono label over a bold value.
function SpecTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-card border border-outline-variant/30 bg-surface-container-lowest p-4">
      <dt className="mb-1 font-label text-label-caps uppercase text-on-surface-variant">{label}</dt>
      <dd className="break-words font-body text-body-md font-bold text-on-surface">{children}</dd>
    </div>
  );
}

// #FVS014-PRODUCT-DETAIL-VIEW
//
// Built against the CONFIRMED `ProductDetail` contract (B3) via
// toProductDetailModel. A 404 from the backend (hidden/deleted/disabled-
// category/renamed/wrong-case slug — B3's own exhaustive list) renders the
// app's real not-found content, matching FVS-014's "rendered as the app's
// real not-found page, not a soft unavailable banner" requirement — this
// is a client-rendered page (this app's established architecture:
// apiClient is a same-origin browser fetch, never used server-side), so
// it renders NotFoundContent directly rather than calling next/navigation's
// `notFound()`, which Next's own docs confirm only for Server Components/
// Server Functions/Route Handlers, not Client Components.
//
// Batch 3 — Stitch Product Details (PAGE-SPECS S4): breadcrumb, 7/5 split
// from 1024px (gallery first when stacked), display H1, the detail price
// role, an action card, spec tiles and the description. Every action keeps
// its own capability gate (can_add_to_cart, can_offer, whatsapp_available)
// and auth branches. Stitch's stock pill, SKU, datasheet, material story,
// reviews and pairings have no data and are not rendered.
export function ProductDetailView({ slug }: ProductDetailViewProps) {
  const productQuery = useProduct(slug);
  const settingsQuery = usePublicSettings();

  if (productQuery.isLoading) {
    return (
      <div className="flex justify-center py-section-mobile tablet:py-section">
        <LoadingSpinner />
      </div>
    );
  }

  if (productQuery.isError) {
    if (productQuery.error.status === 404) {
      return <NotFoundContent />;
    }
    return (
      <Container className="py-12">
        <div className="mx-auto max-w-3xl">
          <Alert variant="error" message="We couldn't load this product. Please try again." />
        </div>
      </Container>
    );
  }

  if (!productQuery.data) {
    // Unreachable in practice: isLoading/isError above already cover
    // every non-success query state. Narrows the type for TypeScript
    // rather than a non-null assertion.
    return null;
  }

  const product = toProductDetailModel(productQuery.data);
  const returnToPath = `/shop/${product.slug}`;
  const hasSpecs =
    product.material !== null || product.colour !== null || product.dimensions !== null || product.productionLeadTimeDays !== null;

  return (
    <Container className="pb-section-mobile pt-8 tablet:pb-section tablet:pt-12">
      <nav aria-label="Breadcrumb" className="mb-8">
        <ol className="flex flex-wrap items-center gap-2 font-label text-label-caps uppercase text-on-surface-variant">
          <li>
            <Link href="/shop" className="rounded-badge hover:text-primary">
              Shop
            </Link>
          </li>
          <li aria-hidden="true">
            <Icon name="chevron-right" className="h-4 w-4" />
          </li>
          <li>
            <Link href={`/shop?category=${product.category.id}`} className="rounded-badge hover:text-primary">
              {product.category.name}
            </Link>
          </li>
          <li aria-hidden="true">
            <Icon name="chevron-right" className="h-4 w-4" />
          </li>
          <li aria-current="page" className="min-w-0 max-w-full truncate text-on-surface">
            {product.name}
          </li>
        </ol>
      </nav>

      <div className="grid grid-cols-1 gap-10 desktop:grid-cols-12 desktop:gap-12">
        <div className="desktop:col-span-7">
          <ProductImageGallery images={product.images} />
        </div>

        <div className="flex min-w-0 flex-col gap-6 desktop:col-span-5">
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <ProductTypeBadge type={product.type} />
              <RatingSummary averageRating={product.averageRating} reviewCount={product.reviewCount} size="md" />
            </div>
            <h1 className="break-words font-display text-display text-on-surface">{product.name}</h1>
            <PriceDisplay amountCents={product.price.amountCents} currency={product.price.currency} size="detail" />
          </div>

          {!product.isAvailable && <UnavailableNotice message="This product is currently unavailable." />}

          {/* One card for every real action: Add to cart (primary), then the
              secondary row — WhatsApp, wishlist — and Make an offer. Each
              renders only what its own capability and auth state allow. */}
          <div className="flex flex-col gap-4 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-6 shadow-sm">
            <AddToCartButton
              productId={product.id}
              productType={product.type}
              productName={product.name}
              canAddToCart={product.capabilities.canAddToCart}
              maxQuantityPerLine={product.maxQuantityPerLine}
              returnToPath={returnToPath}
            />
            {product.capabilities.whatsappAvailable && (
              <WhatsAppChatButton
                normalizedNumber={settingsQuery.data?.whatsappNumber ?? null}
                productName={product.name}
              />
            )}
            {/* Stabilization: a WhatsApp-only product with no WhatsApp number
                configured (a null public setting) left the page with no way
                to order and no explanation. Point to Contact instead. */}
            {product.isAvailable &&
              product.capabilities.whatsappAvailable &&
              !product.capabilities.canAddToCart &&
              settingsQuery.isSuccess &&
              !settingsQuery.data?.whatsappNumber && (
                <p className="font-body text-body-md text-on-surface-variant">
                  This item is ordered over WhatsApp, which isn&apos;t available right now.{" "}
                  <Link href="/contact" className="font-semibold text-primary underline underline-offset-4">
                    Contact us to order it
                  </Link>
                  .
                </p>
              )}
            <WishlistButton productId={product.id} productName={product.name} returnToPath={returnToPath} variant="full" />
            <MakeOfferPanel
              productId={product.id}
              productName={product.name}
              canOffer={product.capabilities.canOffer}
              returnToPath={returnToPath}
            />
          </div>

          {hasSpecs && (
            <section aria-labelledby="product-specs-heading">
              <h2 id="product-specs-heading" className="mb-4 font-headline text-headline-md text-on-surface">
                Specifications
              </h2>
              <dl className="grid grid-cols-2 gap-3 tablet:gap-4">
                {product.material && <SpecTile label="Material">{product.material.name}</SpecTile>}
                {product.colour && <SpecTile label="Colour">{product.colour.name}</SpecTile>}
                {product.dimensions && (
                  <SpecTile label="Dimensions">
                    {product.dimensions.lengthMm} × {product.dimensions.widthMm} × {product.dimensions.heightMm} mm
                  </SpecTile>
                )}
                {product.productionLeadTimeDays !== null && (
                  <SpecTile label="Production lead time">
                    {product.productionLeadTimeDays} day{product.productionLeadTimeDays === 1 ? "" : "s"}
                  </SpecTile>
                )}
              </dl>
            </section>
          )}

          {product.description && (
            <section aria-labelledby="product-description-heading">
              <h2 id="product-description-heading" className="mb-3 font-headline text-headline-md text-on-surface">
                Description
              </h2>
              <p className="whitespace-pre-line break-words font-body text-body-lg text-on-surface-variant">{product.description}</p>
            </section>
          )}
        </div>
      </div>
    </Container>
  );
}
