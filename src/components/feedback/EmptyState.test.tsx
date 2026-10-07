import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "./EmptyState";

// FVS-013-IMPLEMENTATION-PLAN.md T06 — generic empty-state, matching
// bekaa3d-brand-ui's convention: centered neutral icon + one-line
// message + one optional primary action.

describe("EmptyState", () => {
  it("renders the message", () => {
    render(<EmptyState message="No products match your filters." />);
    expect(screen.getByText("No products match your filters.")).toBeInTheDocument();
  });

  it("renders an action button when both actionLabel and onAction are supplied", async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    render(<EmptyState message="No products match your filters." actionLabel="Clear filters" onAction={onAction} />);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it("renders no action button when actionLabel/onAction are not supplied", () => {
    render(<EmptyState message="No products match your filters." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology", () => {
    const { container } = render(<EmptyState message="No products match your filters." />);
    const icon = container.querySelector("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<EmptyState message="No products match your filters." />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
