import type { Metadata } from "next";
import Link from "next/link";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Container } from "@/components/ui/Container";

export const metadata: Metadata = {
  title: "About — Bekaa3D",
};

// FVS-022 — `/about`. Static brand content only (the plan's own "approved
// V1 scope — no CMS" line): a mission statement and what the storefront
// actually offers (physical 3D-printed goods and STL files — both real,
// built product types), with no invented facts — no founding year, team
// bios, customer counts, testimonials, or review content, since none of
// that has an approved source. A server component: nothing here needs
// client-side state or a backend fetch.
//
// Redesign Batch 11 (S8, consistency only): storefront Container, mono
// eyebrow + display h1, the approved copy in one white card, and the two
// existing routes as calls to action. S8's photo hero, stats band, team and
// gallery are omitted — there are no approved assets or numbers for them.
export default function AboutPage() {
  return (
    <Container className="py-12 tablet:py-16">
      <div className="mx-auto max-w-3xl">
        <p className="mb-3 font-label text-label-caps uppercase tracking-widest text-primary">Our story</p>
        <h1 className="font-display text-display text-on-surface">About Bekaa3D</h1>
        <p className="mt-4 text-body-lg text-on-surface-variant">Engineered Grade 3D Solutions.</p>

        <div className="mt-10 flex flex-col gap-6 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-6 text-body-md text-on-surface-variant shadow-sm tablet:p-8">
          <p>
            Bekaa3D designs and produces 3D-printed goods, made to order rather than pulled from a warehouse shelf.
            Every physical piece is printed specifically for the order that requests it, and every STL file is prepared
            for makers who want to print it themselves.
          </p>
          <p>
            Our catalogue covers two kinds of products: ready-made physical prints, available in a choice of material
            and colour where applicable, and downloadable STL files for anyone running their own printer. Each product
            page lists exactly what that item includes and how it can be purchased.
          </p>
          <p>
            We treat precision and finish as the baseline, not the upsell — the same engineering discipline behind our
            name applies whether a part ships to your door or as a file to your print queue.
          </p>
        </div>

        <div className="mt-8 flex flex-col gap-3 tablet:flex-row">
          <Link href="/shop" className={buttonLinkClassName("primary", "lg")}>
            Browse the shop
          </Link>
          <Link href="/contact" className={buttonLinkClassName("secondary", "lg")}>
            Contact us
          </Link>
        </div>
      </div>
    </Container>
  );
}
