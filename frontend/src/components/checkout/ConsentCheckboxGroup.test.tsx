import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConsentCheckboxGroup } from "./ConsentCheckboxGroup";
import { CONSENT_COPY } from "@/lib/checkout/checkoutCopy";

// Exactly the backend's consent booleans (CheckoutRequest accept_terms,
// accept_digital_final_sale, accept_cash_terms): no invented extra
// checkbox. Copy is PENDING LEGAL REVIEW (checkoutCopy.ts).

const NONE = {
  acceptTerms: false,
  acceptDigitalFinalSale: false,
  acceptCashTerms: false,
};

describe("ConsentCheckboxGroup", () => {
  it("terms only for a physical online order, unticked by default", () => {
    render(<ConsentCheckboxGroup showDigital={false} showCash={false} values={NONE} onChange={vi.fn()} errors={{}} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.terms })).not.toBeChecked();
  });

  it("adds the STL final-sale and cash terms boxes only when they apply", () => {
    render(<ConsentCheckboxGroup showDigital showCash values={NONE} onChange={vi.fn()} errors={{}} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.digitalFinalSale })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms })).not.toBeChecked();
  });

  it("reports each change with its own key", async () => {
    const onChange = vi.fn();
    render(<ConsentCheckboxGroup showDigital showCash values={NONE} onChange={onChange} errors={{}} />);
    await userEvent.click(screen.getByRole("checkbox", { name: CONSENT_COPY.digitalFinalSale }));
    expect(onChange).toHaveBeenCalledWith("acceptDigitalFinalSale", true);
    await userEvent.click(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms }));
    expect(onChange).toHaveBeenCalledWith("acceptCashTerms", true);
  });

  it("links an error to its checkbox", () => {
    render(
      <ConsentCheckboxGroup
        showDigital={false}
        showCash={false}
        values={NONE}
        onChange={vi.fn()}
        errors={{ acceptTerms: "Please accept." }}
      />
    );
    const box = screen.getByRole("checkbox", { name: CONSENT_COPY.terms });
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(box).toHaveAccessibleDescription("Please accept.");
  });

  // Redesign Batch 6.
  it("is a group named by its step heading, and each checkbox is named by its full text", () => {
    render(<ConsentCheckboxGroup showDigital showCash values={NONE} onChange={vi.fn()} errors={{}} />);
    expect(screen.getByRole("group", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.terms })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.digitalFinalSale })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms })).not.toBeChecked();
  });
});
