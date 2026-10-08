export type CheckoutSection = "delivery" | "review" | "confirm";

export interface CheckoutStepperProps {
  currentSection: CheckoutSection;
}

const SECTIONS: readonly { id: CheckoutSection; label: string }[] = [
  { id: "delivery", label: "Delivery" },
  { id: "review", label: "Review" },
  { id: "confirm", label: "Confirm" },
];

// #FVS026 — a semantic progress indicator, not an interactive wizard.
// Checkout is a single page with all sections visible simultaneously
// (so a price-conflict banner is never hidden behind a step
// transition) — this component only orients the user within that one
// page. No click handlers, no internal state, no hidden sections.
export function CheckoutStepper({ currentSection }: CheckoutStepperProps) {
  return (
    <nav aria-label="Checkout progress">
      <ol className="flex items-center gap-4">
        {SECTIONS.map((section) => (
          <li key={section.id} aria-current={section.id === currentSection ? "step" : undefined}>
            {section.label}
          </li>
        ))}
      </ol>
    </nav>
  );
}
