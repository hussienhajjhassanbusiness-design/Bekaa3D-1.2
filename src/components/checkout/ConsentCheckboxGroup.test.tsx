import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConsentCheckboxGroup } from "./ConsentCheckboxGroup";

// FVS-026-IMPLEMENTATION-PLAN.md T05 — terms and every digital-product
// consent are independent checkboxes, never one blanket "I agree to
// everything." No legal copy is hardcoded — every label is
// caller-supplied, since no approved legal text exists in this
// repository. Every checkbox defaults to unchecked.

describe("ConsentCheckboxGroup", () => {
  it("renders the terms checkbox with the caller-supplied label, unchecked by default", () => {
    render(<ConsentCheckboxGroup termsLabel="I agree to the Terms of Service." termsAccepted={false} onTermsChange={vi.fn()} />);
    const checkbox = screen.getByRole("checkbox", { name: "I agree to the Terms of Service." });
    expect(checkbox).not.toBeChecked();
  });

  it("toggling the terms checkbox calls onTermsChange with the new value", async () => {
    const onTermsChange = vi.fn();
    const user = userEvent.setup();
    render(<ConsentCheckboxGroup termsLabel="I agree to the Terms." termsAccepted={false} onTermsChange={onTermsChange} />);

    await user.click(screen.getByRole("checkbox", { name: "I agree to the Terms." }));

    expect(onTermsChange).toHaveBeenCalledWith(true);
  });

  it("renders no digital-consent checkboxes when none are supplied (a cart with no STL lines)", () => {
    render(<ConsentCheckboxGroup termsLabel="I agree to the Terms." termsAccepted={false} onTermsChange={vi.fn()} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  });

  it("renders one independent checkbox per supplied digital consent with its own label", () => {
    render(
      <ConsentCheckboxGroup
        termsLabel="I agree to the Terms."
        termsAccepted={false}
        onTermsChange={vi.fn()}
        digitalConsents={[
          { productId: "prod-1", label: "I understand Dragon STL is a final digital sale.", accepted: false },
          { productId: "prod-2", label: "I understand Castle STL is a final digital sale.", accepted: false },
        ]}
        onDigitalConsentChange={vi.fn()}
      />
    );

    expect(screen.getByRole("checkbox", { name: "I understand Dragon STL is a final digital sale." })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "I understand Castle STL is a final digital sale." })).toBeInTheDocument();
  });

  it("toggling one digital consent never affects another or the terms checkbox", async () => {
    const onDigitalConsentChange = vi.fn();
    const onTermsChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ConsentCheckboxGroup
        termsLabel="I agree to the Terms."
        termsAccepted={false}
        onTermsChange={onTermsChange}
        digitalConsents={[
          { productId: "prod-1", label: "Consent for Dragon STL.", accepted: false },
          { productId: "prod-2", label: "Consent for Castle STL.", accepted: false },
        ]}
        onDigitalConsentChange={onDigitalConsentChange}
      />
    );

    await user.click(screen.getByRole("checkbox", { name: "Consent for Dragon STL." }));

    expect(onDigitalConsentChange).toHaveBeenCalledWith("prod-1", true);
    expect(onTermsChange).not.toHaveBeenCalled();
  });

  it("every digital-consent checkbox starts unchecked by default, never pre-checked", () => {
    render(
      <ConsentCheckboxGroup
        termsLabel="I agree to the Terms."
        termsAccepted={false}
        onTermsChange={vi.fn()}
        digitalConsents={[{ productId: "prod-1", label: "Consent for Dragon STL.", accepted: false }]}
        onDigitalConsentChange={vi.fn()}
      />
    );
    expect(screen.getByRole("checkbox", { name: "Consent for Dragon STL." })).not.toBeChecked();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ConsentCheckboxGroup termsLabel="I agree to the Terms." termsAccepted={false} onTermsChange={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
