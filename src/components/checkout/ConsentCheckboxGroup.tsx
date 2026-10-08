export interface DigitalConsentItem {
  productId: string;
  label: string;
  accepted: boolean;
}

export interface ConsentCheckboxGroupProps {
  // Caller-supplied — no legal copy is hardcoded anywhere, since no
  // approved text exists in this repository.
  termsLabel: string;
  termsAccepted: boolean;
  onTermsChange: (checked: boolean) => void;
  // Populated by the caller from the cart's STL lines (via
  // isStlLine, FVS-025) — this component has no cart-filtering logic
  // of its own.
  digitalConsents?: readonly DigitalConsentItem[];
  onDigitalConsentChange?: (productId: string, checked: boolean) => void;
}

// #FVS026 — terms and every digital-product consent are independent
// checkboxes, never one blanket "I agree to everything." Every
// checkbox defaults to unchecked; this component never pre-checks
// one under any prop combination.
export function ConsentCheckboxGroup({
  termsLabel,
  termsAccepted,
  onTermsChange,
  digitalConsents,
  onDigitalConsentChange,
}: ConsentCheckboxGroupProps) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-start gap-2 text-body text-text-primary">
        <input type="checkbox" checked={termsAccepted} onChange={(event) => onTermsChange(event.target.checked)} />
        {termsLabel}
      </label>

      {digitalConsents?.map((item) => (
        <label key={item.productId} className="flex items-start gap-2 text-body text-text-primary">
          <input
            type="checkbox"
            checked={item.accepted}
            onChange={(event) => onDigitalConsentChange?.(item.productId, event.target.checked)}
          />
          {item.label}
        </label>
      ))}
    </div>
  );
}
