import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CheckoutStepHeading } from "./CheckoutStepHeading";

describe("CheckoutStepHeading", () => {
  it("renders an h2 whose name is the title alone (the step circle is decorative)", () => {
    render(<CheckoutStepHeading step={2} title="Payment" />);
    expect(screen.getByRole("heading", { level: 2, name: "Payment" })).toBeInTheDocument();
    expect(screen.getByText("2").closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("as a legend, it names its fieldset", () => {
    render(
      <fieldset>
        <CheckoutStepHeading as="legend" step={1} title="Delivery or pickup" />
        <input type="radio" aria-label="Delivery" />
      </fieldset>
    );
    expect(screen.getByRole("group", { name: "Delivery or pickup" })).toBeInTheDocument();
  });

  it("complete swaps the number for a decorative check, keeping the same accessible name", () => {
    render(<CheckoutStepHeading step={3} title="Confirm" complete />);
    expect(screen.queryByText("3")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Confirm" })).toBeInTheDocument();
  });
});
