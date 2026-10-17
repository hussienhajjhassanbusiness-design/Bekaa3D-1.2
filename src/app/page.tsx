import { HeroSection } from "@/components/home/HeroSection";
import { FeaturedProductsSection } from "@/components/home/FeaturedProductsSection";
import { CategoryShowcaseSection } from "@/components/home/CategoryShowcaseSection";
import { WhyChooseSection } from "@/components/home/WhyChooseSection";

// REAL STOREFRONT INTEGRATION — PHASE 1: replaces the Hero-only
// placeholder with the real Bekaa3D home surface now that /shop and
// /about are actually mounted. HeroSection is reused unchanged (no
// second hero component) — only its CTAs are now filled in, since a
// currently-valid destination finally exists for them. Featured products
// and categories come from the real backend (FVS-013's own
// ProductGrid/ProductCard, FVS-010's own category list) — if either
// fetch returns nothing, that section omits itself rather than showing a
// placeholder. Why Choose Bekaa3D is static, honest brand copy (no
// invented stats/testimonials). Still a server component at the root:
// the data-fetching pieces are client components nested inside it, same
// pattern as every other page in this app.
export default function Home() {
  return (
    <div className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-brand-lime/20 blur-3xl" />
        <div className="absolute -right-20 top-40 h-80 w-80 rounded-full bg-brand-dark-green/10 blur-3xl" />
        <div className="absolute left-1/2 top-1/2 hidden h-48 w-48 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-2xl border border-brand-lime/30 tablet:block" />
      </div>
      <div className="mx-auto max-w-3xl px-4 py-16 text-center tablet:py-24">
        <HeroSection
          primaryCta={{ label: "Shop Now", href: "/shop" }}
          secondaryCta={{ label: "Learn More", href: "/about" }}
        />
      </div>
      <div className="mx-auto max-w-7xl px-4 pb-16 tablet:px-6 desktop:px-8">
        <FeaturedProductsSection />
        <CategoryShowcaseSection />
        <WhyChooseSection />
      </div>
    </div>
  );
}
