"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Container } from "@/components/ui/Container";
import { Icon } from "@/components/ui/Icon";
import { productsApi, productsKeys } from "@/lib/catalog/productsApi";
import type { ProductsQueryParams } from "@/lib/catalog/productTypes";
import {
  discountAmount,
  discountHeadline,
  formatPromotionDate,
  promotionScopePhrase,
} from "@/lib/promotions/promotionFormat";
import { useActivePromotions } from "@/lib/promotions/promotionsApi";
import { PROMOTION_CURRENCY } from "@/lib/promotions/promotionTypes";

const COLLAGE_SIZE = 3;

// #HOME-PROMOTION-BANNER — Stitch home "Promo banner" (PAGE-SPECS S1 §4,
// COMPONENT-SPECS §52 dark promo): a rounded-banner on-surface (#141b2b)
// panel, white display discount, lime campaign line, body, lime CTA, imagery
// on the right.
//
// Every word comes from the server's active promotion (GET /api/v1/promotions,
// soonest ending first). With none active — or while loading, or on error —
// it renders nothing: no placeholder, and none of the mock-up's sample
// campaign copy is ever shown. The CTA is "Shop promotion", not Stitch's
// redemption wording: nothing is redeemed, prices are already lowered. It
// links to /shop?promotion=<id>, the server's own list of covered products.
//
// The imagery is the real cover images of covered products (decorative: the
// campaign text carries the meaning). No backend image exists, and the
// Google-hosted Stitch collage is never used; with no covers, the text spans
// the panel.
export function HomePromotionBanner() {
  const promotions = useActivePromotions();
  const promotion = promotions.data?.items[0];
  const coverParams: ProductsQueryParams = { promotion_id: promotion?.id, limit: COLLAGE_SIZE };
  const covers = useQuery({
    queryKey: [...productsKeys.list(coverParams), "promotion-covers"],
    queryFn: () => productsApi.listProducts(coverParams),
    enabled: promotion !== undefined,
  });

  if (!promotion) return null;

  const images = (covers.data?.items ?? [])
    .map((item) => item.cover_image?.url)
    .filter((url): url is string => Boolean(url))
    .slice(0, COLLAGE_SIZE);
  const amount = discountAmount(promotion.discount_type, promotion.discount_value, PROMOTION_CURRENCY);
  const headingId = `promotion-${promotion.id}-heading`;

  return (
    <section aria-labelledby={headingId} className="py-section-mobile tablet:py-section">
      <Container>
        <div className="relative isolate overflow-hidden rounded-banner bg-on-surface px-6 py-12 text-center tablet:px-12 tablet:py-16 tablet:text-left desktop:px-12 desktop:py-20">
          <div
            aria-hidden="true"
            className="absolute -bottom-24 -left-24 -z-10 h-80 w-80 rounded-full bg-secondary-fixed/10 blur-3xl"
          />
          <div className={`grid items-center gap-12 ${images.length > 0 ? "tablet:grid-cols-2" : ""}`}>
            <div className="min-w-0">
              {promotion.badge_text && (
                <p className="mb-4 font-label text-label-caps uppercase tracking-widest text-secondary-fixed">
                  {promotion.badge_text}
                </p>
              )}
              <h2 id={headingId} className="mb-6 break-words font-display text-headline-lg text-white tablet:text-display">
                {discountHeadline(promotion.discount_type, promotion.discount_value, PROMOTION_CURRENCY)}
                <br />
                <span className="text-secondary-fixed">{promotion.name}</span>
              </h2>
              <p className="mx-auto mb-8 max-w-md font-body text-body-lg text-white/70 tablet:mx-0">
                Save {amount} {promotionScopePhrase(promotion.scope)} until{" "}
                <time dateTime={promotion.ends_at}>{formatPromotionDate(promotion.ends_at)}</time>. Prices in the shop
                and at checkout already include the discount.
              </p>
              <Link
                href={`/shop?promotion=${encodeURIComponent(promotion.id)}`}
                className="inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-xl bg-secondary-fixed px-10 py-5 font-label text-label-caps uppercase text-on-secondary-fixed shadow-lg transition-transform duration-200 ease-standard hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-fixed motion-reduce:transition-none motion-reduce:hover:scale-100 sm:w-auto"
              >
                Shop promotion
                <Icon name="arrow-forward" className="h-5 w-5" />
              </Link>
            </div>
            {images.length > 0 && (
              <div aria-hidden="true" className="hidden grid-cols-3 gap-3 tablet:grid">
                {images.map((src, index) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={src}
                    src={src}
                    alt=""
                    loading="lazy"
                    className={`aspect-square w-full rounded-card object-cover shadow-xl ${
                      index === 1 ? "translate-y-6" : ""
                    } ${images.length === 1 ? "col-span-3" : ""}`}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </Container>
    </section>
  );
}
