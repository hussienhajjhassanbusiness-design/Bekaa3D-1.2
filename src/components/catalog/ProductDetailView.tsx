"use client";

import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useProduct } from "@/lib/catalog/useProduct";
import { toProductDetailModel } from "@/lib/catalog/productAdapters";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { AddToCartButton } from "./AddToCartButton";
import { PriceDisplay } from "./PriceDisplay";
import { ProductImageGallery } from "./ProductImageGallery";
import { ProductTypeBadge } from "./ProductTypeBadge";
import { UnavailableNotice } from "./UnavailableNotice";
import { WhatsAppChatButton } from "./WhatsAppChatButton";

export interface ProductDetailViewProps {
  slug: string;
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
export function ProductDetailView({ slug }: ProductDetailViewProps) {
  const productQuery = useProduct(slug);
  const settingsQuery = usePublicSettings();
  const { isAuthenticated } = useAuth();

  if (productQuery.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (productQuery.isError) {
    if (productQuery.error.status === 404) {
      return <NotFoundContent />;
    }
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Alert variant="error" message="We couldn't load this product. Please try again." />
      </div>
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

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 tablet:px-6 desktop:px-8">
      <div className="grid grid-cols-1 gap-8 tablet:grid-cols-2">
        <ProductImageGallery images={product.images} />

        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <ProductTypeBadge type={product.type} />
            <span className="text-caption uppercase tracking-label text-text-secondary">{product.category.name}</span>
          </div>

          <h1 className="text-h1 font-bold text-text-primary">{product.name}</h1>

          <div className="text-h2 font-semibold text-text-primary">
            <PriceDisplay amountCents={product.price.amountCents} currency={product.price.currency} />
          </div>

          {(product.material || product.colour) && (
            <dl className="flex flex-wrap gap-6 text-body text-text-secondary">
              {product.material && (
                <div>
                  <dt className="inline font-semibold text-text-primary">Material: </dt>
                  <dd className="inline">{product.material.name}</dd>
                </div>
              )}
              {product.colour && (
                <div>
                  <dt className="inline font-semibold text-text-primary">Colour: </dt>
                  <dd className="inline">{product.colour.name}</dd>
                </div>
              )}
            </dl>
          )}

          {product.dimensions && (
            <p className="text-body text-text-secondary">
              Dimensions: {product.dimensions.lengthMm} × {product.dimensions.widthMm} × {product.dimensions.heightMm} mm
            </p>
          )}
          {product.productionLeadTimeDays !== null && (
            <p className="text-body text-text-secondary">
              Production lead time: {product.productionLeadTimeDays} day{product.productionLeadTimeDays === 1 ? "" : "s"}
            </p>
          )}

          {!product.isAvailable && <UnavailableNotice message="This product is currently unavailable." />}

          {product.description && <p className="text-body text-text-primary">{product.description}</p>}

          <div className="mt-2 flex flex-wrap gap-3">
            {product.capabilities.canAddToCart && (
              <AddToCartButton isAuthenticated={isAuthenticated} returnToPath={returnToPath} />
            )}
            {product.capabilities.whatsappAvailable && (
              <WhatsAppChatButton
                normalizedNumber={settingsQuery.data?.whatsappNumber ?? null}
                productName={product.name}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
