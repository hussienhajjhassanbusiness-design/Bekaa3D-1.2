import type { Metadata } from "next";

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
export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 tablet:px-6 desktop:px-8">
      <h1 className="text-h1 font-bold text-text-primary">About Bekaa3D</h1>
      <p className="mt-4 text-body-lg text-text-secondary">Engineered Grade 3D Solutions.</p>

      <div className="mt-8 flex flex-col gap-6 text-body text-text-primary">
        <p>
          Bekaa3D designs and produces 3D-printed goods, made to order rather than pulled from a
          warehouse shelf. Every physical piece is printed specifically for the order that requests
          it, and every STL file is prepared for makers who want to print it themselves.
        </p>
        <p>
          Our catalogue covers two kinds of products: ready-made physical prints, available in a
          choice of material and colour where applicable, and downloadable STL files for anyone
          running their own printer. Each product page lists exactly what that item includes and how
          it can be purchased.
        </p>
        <p>
          We treat precision and finish as the baseline, not the upsell — the same engineering
          discipline behind our name applies whether a part ships to your door or as a file to your
          print queue.
        </p>
      </div>
    </div>
  );
}
