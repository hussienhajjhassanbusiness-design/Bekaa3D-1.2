import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PaymentVerificationErrorState } from "./PaymentVerificationErrorState";

// FVS-027-IMPLEMENTATION-PLAN.md T06 — "Verification is temporarily
// unavailable" copy; never renders a raw network/server exception
// message.

describe("PaymentVerificationErrorState", () => {
  it("renders a safe, generic unavailable message", () => {
    render(<PaymentVerificationErrorState onRetry={vi.fn()} />);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
  });

  it("calls onRetry only on an explicit click, never automatically", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<PaymentVerificationErrorState onRetry={onRetry} />);

    expect(onRetry).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("never renders a raw network/server exception message", () => {
    render(<PaymentVerificationErrorState onRetry={vi.fn()} />);
    expect(screen.queryByText(/typeerror|fetch failed|networkerror|stack/i)).not.toBeInTheDocument();
  });
});
