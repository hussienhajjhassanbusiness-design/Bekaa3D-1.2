import { HeroSection } from "@/components/home/HeroSection";

// FVS-022-IMPLEMENTATION-PLAN.md follow-up — replaces the FVS-001
// placeholder with the real Bekaa3D home surface. Reuses HeroSection
// unchanged (no second hero component); adds only a decorative,
// aria-hidden background treatment and layout spacing built from
// existing brand tokens (tokens.md) — no new dependency, no
// animation. No product data, no About copy, no WhatsApp number, and
// no CTA are added here, since none of those has an approved source
// yet (plan §6) — the composition stays Hero-only rather than
// fabricating content to fill the page. A server component: nothing
// here needs client-side state, and nothing fetches public
// settings/products.
export default function Home() {
  return (
    <div className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-brand-lime/20 blur-3xl" />
        <div className="absolute -right-20 top-40 h-80 w-80 rounded-full bg-brand-dark-green/10 blur-3xl" />
        <div className="absolute left-1/2 top-1/2 hidden h-48 w-48 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-2xl border border-brand-lime/30 tablet:block" />
      </div>
      <div className="mx-auto max-w-3xl px-4 py-16 text-center tablet:py-24">
        <HeroSection />
      </div>
    </div>
  );
}
