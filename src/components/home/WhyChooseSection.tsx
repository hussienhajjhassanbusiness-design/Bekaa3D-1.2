import { Container } from "@/components/ui/Container";
import { Icon, type IconName } from "@/components/ui/Icon";
import { SectionHeader } from "@/components/ui/SectionHeader";

interface WhyChoosePoint {
  icon: IconName;
  heading: string;
  body: string;
}

// Static, honest brand copy only — no invented statistics, customer
// counts, or testimonials (none has an approved source yet). Describes
// real, built capabilities: both product types this storefront actually
// sells, and the made-to-order model stated in the backend's own contract
// notes (B3: "no stock quantity ... products are made to order").
const POINTS: readonly WhyChoosePoint[] = [
  {
    icon: "deployed-code",
    heading: "Made to order",
    body: "Every physical piece is printed for the order that requests it — no warehouse stock sitting on a shelf.",
  },
  {
    icon: "download",
    heading: "Physical or digital",
    body: "Buy a finished print, or get the STL file and print it yourself on your own machine.",
  },
  {
    icon: "verified",
    heading: "Engineering-grade finish",
    body: "Precision and surface quality are the standard we hold every print to, not an optional upgrade.",
  },
];

// Batch 3 — Stitch "Precision as Standard" feature tiles (COMPONENT-SPECS
// §14): centred section header, then tiles with a 64px tonal icon box that
// turns primary on hover (rotation off under reduced motion). Three real
// points, so the tiles are larger cards rather than Stitch's six small ones.
export function WhyChooseSection() {
  return (
    <section aria-labelledby="why-choose-heading" className="bg-surface-container-low py-section-mobile tablet:py-section">
      <Container>
        <SectionHeader
          headingId="why-choose-heading"
          title="Why Choose Bekaa3D"
          description="The same standard whether a part ships to your door or as a file to your print queue."
        />
        <ul className="grid grid-cols-1 gap-gutter tablet:grid-cols-3">
          {POINTS.map((point) => (
            <li
              key={point.heading}
              className="group rounded-card border border-outline-variant/30 bg-surface-container-lowest p-8 text-center shadow-sm"
            >
              <span
                aria-hidden="true"
                className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-panel bg-surface-container text-primary transition-[transform,background-color,color] duration-300 ease-standard group-hover:rotate-6 group-hover:bg-primary group-hover:text-on-primary motion-reduce:transition-none motion-reduce:group-hover:rotate-0"
              >
                <Icon name={point.icon} className="h-8 w-8" />
              </span>
              <h3 className="mb-2 font-headline text-headline-md text-on-surface">{point.heading}</h3>
              <p className="font-body text-body-md text-on-surface-variant">{point.body}</p>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
