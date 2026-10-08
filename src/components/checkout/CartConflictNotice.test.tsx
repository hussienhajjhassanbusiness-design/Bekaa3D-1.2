import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CartConflictNotice } from "./CartConflictNotice";
import type { CartConflictLine } from "@/lib/checkout/checkoutModels";

// FVS-026-IMPLEMENTATION-PLAN.md T06 — renders each line's own
// caller-supplied message individually, never collapsed into a
// generic "Checkout failed."

const LINES: readonly CartConflictLine[] = [
  { lineId: "line-1", kind: "unavailable", message: "Garden Gnome is no longer available." },
  { lineId: "line-2", kind: "quantity-adjusted", message: "Dragon STL quantity was adjusted to 1." },
];

describe("CartConflictNotice", () => {
  it("renders every line's distinct message", () => {
    render(<CartConflictNotice lines={LINES} />);
    expect(screen.getByText("Garden Gnome is no longer available.")).toBeInTheDocument();
    expect(screen.getByText("Dragon STL quantity was adjusted to 1.")).toBeInTheDocument();
  });

  it("never renders a generic fallback string when lines are non-empty", () => {
    render(<CartConflictNotice lines={LINES} />);
    expect(screen.queryByText(/checkout failed/i)).not.toBeInTheDocument();
  });

  it("renders nothing when there are no conflict lines", () => {
    const { container } = render(<CartConflictNotice lines={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CartConflictNotice lines={LINES} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
