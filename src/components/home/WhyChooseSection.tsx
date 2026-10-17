interface WhyChoosePoint {
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
    heading: "Made to order",
    body: "Every physical piece is printed for the order that requests it — no warehouse stock sitting on a shelf.",
  },
  {
    heading: "Physical or digital",
    body: "Buy a finished print, or get the STL file and print it yourself on your own machine.",
  },
  {
    heading: "Engineering-grade finish",
    body: "Precision and surface quality are the standard we hold every print to, not an optional upgrade.",
  },
];

export function WhyChooseSection() {
  return (
    <section aria-labelledby="why-choose-heading" className="mt-12">
      <h2 id="why-choose-heading" className="text-h2 font-bold text-text-primary">
        Why Choose Bekaa3D
      </h2>
      <div className="mt-4 grid grid-cols-1 gap-6 tablet:grid-cols-3">
        {POINTS.map((point) => (
          <div key={point.heading} className="rounded-md border border-border-default p-4">
            <h3 className="text-h4 font-semibold text-text-primary">{point.heading}</h3>
            <p className="mt-2 text-body text-text-secondary">{point.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
