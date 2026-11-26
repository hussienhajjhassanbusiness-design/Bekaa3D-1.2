import { Icon } from "@/components/ui/Icon";

export interface CheckoutStepHeadingProps {
  step: number;
  title: string;
  // Decoration only: a filled circle with a check once the customer has
  // made this step's choice. It never gates anything (validation does).
  complete?: boolean;
  id?: string;
  // "legend" when the step is a fieldset (the group name is then the h2
  // text); "div" for a step without form controls.
  as?: "legend" | "div";
}

// #CHECKOUT-STEP-HEADING (redesign Batch 6, COMPONENT-SPECS §33)
//
// The numbered step header: a 32px circle (filled + check when complete,
// 2px primary outline otherwise) beside an h2. The circle is aria-hidden;
// the h2 text is the accessible name. Rendered as a <legend> (HTML allows
// heading content there), a fieldset's group name and the page's heading
// outline come from the same visible text.
export function CheckoutStepHeading({
  step,
  title,
  complete = false,
  id,
  as: Wrapper = "div",
}: CheckoutStepHeadingProps) {
  return (
    <Wrapper className="mb-6 flex w-full items-center gap-4">
      <span
        aria-hidden="true"
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-label text-label-caps font-bold ${
          complete ? "bg-primary text-on-primary" : "border-2 border-primary text-primary"
        }`}
      >
        {complete ? <Icon name="check" className="h-5 w-5" strokeWidth={2.25} /> : step}
      </span>
      <h2 id={id} className="min-w-0 break-words font-headline text-headline-lg text-on-surface">
        {title}
      </h2>
    </Wrapper>
  );
}
