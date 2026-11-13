import { HeroSection } from "@/components/home/HeroSection";
import { FeaturedProductsSection } from "@/components/home/FeaturedProductsSection";
import { CategoryShowcaseSection } from "@/components/home/CategoryShowcaseSection";
import { WhyChooseSection } from "@/components/home/WhyChooseSection";
import { CustomRequestCtaSection } from "@/components/home/CustomRequestCtaSection";

// REAL STOREFRONT INTEGRATION — PHASE 1: the real Bekaa3D home surface.
// Featured products and categories come from the real backend (FVS-013's
// own ProductGrid/ProductCard, FVS-010's own category list) — if either
// fetch returns nothing, that section omits itself rather than showing a
// placeholder. Why Choose Bekaa3D is static, honest brand copy (no
// invented stats/testimonials). Still a server component at the root:
// the data-fetching pieces are client components nested inside it.
//
// Batch 3 — Stitch home (PAGE-SPECS S1) in its section order, full-width
// bands with alternating surfaces and the 96px (64px mobile) rhythm:
// split hero → category bento → featured products → feature tiles → CTA
// panel. Stitch's promo banner, STL strip and testimonials have no real
// data and are not built (redesign plan, Batch 3 deviations).
export default function Home() {
  return (
    <>
      <HeroSection
        supportingCopy="Ready-made physical prints in a choice of material and colour, and downloadable STL files for anyone running their own printer."
        primaryCta={{ label: "Shop Now", href: "/shop" }}
        secondaryCta={{ label: "Learn More", href: "/about" }}
      />
      <CategoryShowcaseSection />
      <FeaturedProductsSection />
      <WhyChooseSection />
      <CustomRequestCtaSection />
    </>
  );
}
