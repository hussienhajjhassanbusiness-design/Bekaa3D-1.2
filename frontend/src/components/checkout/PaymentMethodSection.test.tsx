import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PaymentMethodSection } from "./PaymentMethodSection";
import { PAYMENT_COPY } from "@/lib/checkout/checkoutCopy";

// PaymentMethod enum: online | cash (backend 2dfb27b). No provider names,
// no card/Whish UI. Cash follows public settings + the physical-only rule.

const MAX = { amountCents: 10000, currency: "USD" };

describe("PaymentMethodSection", () => {
  it("online only when cash is not offered", () => {
    render(
      <PaymentMethodSection value={null} onChange={vi.fn()} cash={{ offered: false, eligible: false, maxTotal: MAX }} />
    );
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: new RegExp(PAYMENT_COPY.onlineLabel) })).toBeInTheDocument();
    expect(screen.queryByText(/whish|card/i)).not.toBeInTheDocument();
  });

  it("cash eligible: selectable, with the public cash limit as information", async () => {
    const onChange = vi.fn();
    render(
      <PaymentMethodSection value={null} onChange={onChange} cash={{ offered: true, eligible: true, maxTotal: MAX }} />
    );
    const cash = screen.getByRole("radio", {
      name: new RegExp(PAYMENT_COPY.cashLabel),
    });
    expect(cash).toBeEnabled();
    expect(cash).toHaveAccessibleDescription(/Available for orders up to \$100\.00\./);
    await userEvent.click(cash);
    expect(onChange).toHaveBeenCalledWith("cash");
  });

  it("cash offered but not eligible (STL in the cart): disabled with the reason", () => {
    render(
      <PaymentMethodSection value={null} onChange={vi.fn()} cash={{ offered: true, eligible: false, maxTotal: MAX }} />
    );
    const cash = screen.getByRole("radio", {
      name: new RegExp(PAYMENT_COPY.cashLabel),
    });
    expect(cash).toBeDisabled();
    expect(cash).toHaveAccessibleDescription(PAYMENT_COPY.cashNeedsPhysical);
  });

  // Redesign Batch 6.
  it("is a group named by its step heading", () => {
    render(
      <PaymentMethodSection value={null} onChange={vi.fn()} cash={{ offered: true, eligible: true, maxTotal: MAX }} />
    );
    expect(screen.getByRole("group", { name: "Payment" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Payment" })).toBeInTheDocument();
  });

  it("an ineligible cash option says Not available in text, not only by fading", () => {
    render(
      <PaymentMethodSection value={null} onChange={vi.fn()} cash={{ offered: true, eligible: false, maxTotal: MAX }} />
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("names no payment provider and shows no card fields", () => {
    render(
      <PaymentMethodSection value={null} onChange={vi.fn()} cash={{ offered: true, eligible: true, maxTotal: MAX }} />
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/visa|mastercard|paypal|stripe|whish/i)).not.toBeInTheDocument();
  });
});
