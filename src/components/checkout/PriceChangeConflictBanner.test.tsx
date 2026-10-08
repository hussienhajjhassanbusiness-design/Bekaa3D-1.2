import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PriceChangeConflictBanner } from "./PriceChangeConflictBanner";
import type { PriceConflictLine } from "@/lib/checkout/checkoutModels";

// FVS-026-IMPLEMENTATION-PLAN.md T06 — #SECURITY-CHECKOUT-PRICE-CONFIRMATION.
// Blocks progress, needs immediate attention. Never auto-retries --
// onReconfirm is the only callback this component ever calls, and
// only on an explicit click.

const LINES: readonly PriceConflictLine[] = [
  { lineId: "line-1", productDisplayName: "Garden Gnome", oldPriceCents: 1000, newPriceCents: 1200, currency: "USD" },
];

describe("PriceChangeConflictBanner", () => {
  it("renders as an assertive alert", () => {
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={vi.fn()} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("aria-live", "assertive");
  });

  it("renders every affected line's old and new price distinctly", () => {
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={vi.fn()} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText("$12.00")).toBeInTheDocument();
  });

  it("never calls onReconfirm automatically on mount", () => {
    const onReconfirm = vi.fn();
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={onReconfirm} />);
    expect(onReconfirm).not.toHaveBeenCalled();
  });

  it("calls onReconfirm only on an explicit click of the Reconfirm button", async () => {
    const onReconfirm = vi.fn();
    const user = userEvent.setup();
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={onReconfirm} />);

    await user.click(screen.getByRole("button", { name: /reconfirm/i }));

    expect(onReconfirm).toHaveBeenCalledTimes(1);
  });

  it("renders exactly one Reconfirm button, never a second auto-retry control", () => {
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={vi.fn()} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<PriceChangeConflictBanner lines={LINES} onReconfirm={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
