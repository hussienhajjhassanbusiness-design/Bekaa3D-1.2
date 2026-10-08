import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderConcurrencyConflictNotice } from "./OrderConcurrencyConflictNotice";

// FVS-030-IMPLEMENTATION-PLAN.md T08 — generic conflict notice, no
// invented 409/412/version-mismatch code anywhere
// (#SECURITY-ORDER-CONCURRENCY-REFETCH). Explains, offers a refresh,
// never silently overwrites.

describe("OrderConcurrencyConflictNotice", () => {
  it("renders the caller-supplied message", () => {
    render(<OrderConcurrencyConflictNotice message="This order changed since you loaded it." onRefresh={vi.fn()} />);
    expect(screen.getByText("This order changed since you loaded it.")).toBeInTheDocument();
  });

  it("clicking refresh calls onRefresh", async () => {
    const onRefresh = vi.fn();
    const user = userEvent.setup();
    render(<OrderConcurrencyConflictNotice message="Conflict" onRefresh={onRefresh} />);

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("never invents a version/conflict code in its own text", () => {
    render(<OrderConcurrencyConflictNotice message="Conflict" onRefresh={vi.fn()} />);
    expect(screen.queryByText(/409|412|version mismatch/i)).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call on its own", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OrderConcurrencyConflictNotice message="Conflict" onRefresh={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
