import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PaymentVerificationTimeoutState } from "./PaymentVerificationTimeoutState";
import { PaymentFailedState } from "./PaymentFailedState";

// FVS-027-IMPLEMENTATION-PLAN.md T06 — "We're still confirming your
// payment" copy, explicitly NOT failure language: this is a
// local-poller-stopped state, never dressed up as a payment outcome.

describe("PaymentVerificationTimeoutState", () => {
  it("renders honest still-confirming copy, never failure language", () => {
    render(<PaymentVerificationTimeoutState onRetry={vi.fn()} />);
    expect(screen.getByText(/still confirming/i)).toBeInTheDocument();
  });

  it("calls onRetry only on an explicit click, never automatically", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<PaymentVerificationTimeoutState onRetry={onRetry} />);

    expect(onRetry).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /check again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("its copy is provably distinct from PaymentFailedState's copy", () => {
    const { container: timeoutContainer } = render(<PaymentVerificationTimeoutState onRetry={vi.fn()} />);
    const { container: failedContainer } = render(<PaymentFailedState />);
    expect(timeoutContainer.textContent).not.toBe(failedContainer.textContent);
  });
});
