import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminOrderDetail } from "./AdminOrderDetail";
import type { AdminOrderModel } from "@/lib/admin/adminOrderModel";

// FVS-030-IMPLEMENTATION-PLAN.md T06 — composes OrderSummaryDisplay
// (reused from FVS-029) + InternalNoteEditor + a list of AdminOrderLine.
// No payment-provider secret/raw payload prop exists on this component
// structurally (AdminOrderModel reuses OrderSummaryModel verbatim).

function makeOrder(overrides: Partial<AdminOrderModel> = {}): AdminOrderModel {
  return {
    id: "order-1",
    displayDate: "Jan 1, 2026",
    statusLabel: "Processing",
    internalNote: "Called customer re: delay",
    summary: { currency: "USD", totalCents: 5999 },
    lines: [
      {
        id: "line-1",
        productDisplayName: "Garden Gnome",
        productType: "physical",
        quantity: 1,
        unitPriceCents: 4999,
        lineTotalCents: 4999,
        currency: "USD",
        statusLabel: "Processing",
        availableActions: [{ id: "move-to-production", label: "Move to production", requiresConfirmation: false }],
      },
    ],
    ...overrides,
  };
}

describe("AdminOrderDetail", () => {
  it("renders the order summary via OrderSummaryDisplay", () => {
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={vi.fn()} onSaveNote={vi.fn()} />);
    expect(screen.getByText("$59.99")).toBeInTheDocument();
  });

  it("renders the internal note editor with the order's current note", () => {
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={vi.fn()} onSaveNote={vi.fn()} />);
    expect(screen.getByText("Internal note — not visible to customers")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Called customer re: delay")).toBeInTheDocument();
  });

  it("saving the note calls onSaveNote with the edited text", async () => {
    const onSaveNote = vi.fn();
    const user = userEvent.setup();
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={vi.fn()} onSaveNote={onSaveNote} />);

    const textarea = screen.getByDisplayValue("Called customer re: delay");
    await user.clear(textarea);
    await user.type(textarea, "Updated note");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSaveNote).toHaveBeenCalledWith("Updated note");
  });

  it("renders an AdminOrderLine per order line, with transition actions", () => {
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={vi.fn()} onSaveNote={vi.fn()} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to production" })).toBeInTheDocument();
  });

  it("selecting a line action calls the composed callback with (lineId, actionId)", async () => {
    const onSelectAction = vi.fn();
    const user = userEvent.setup();
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={onSelectAction} onSaveNote={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Move to production" }));

    expect(onSelectAction).toHaveBeenCalledWith("line-1", "move-to-production");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AdminOrderDetail order={makeOrder()} onSelectAction={vi.fn()} onSaveNote={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
