import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CancellableOrderLine } from "./CancellableOrderLine";
import { OrderLineItem } from "./OrderLineItem";
import type { CancellableOrderLineModel } from "@/lib/orders/orderExceptionModel";

// FVS-031-IMPLEMENTATION-PLAN.md T06 — composes FVS-029's
// OrderLineItem (reused completely unmodified) + CancelOrderLineButton,
// mirroring AdminOrderLine's exact composition structure
// (#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY).

function makeLine(overrides: Partial<CancellableOrderLineModel> = {}): CancellableOrderLineModel {
  return {
    id: "line-1",
    productDisplayName: "Garden Gnome",
    productType: "physical",
    quantity: 1,
    unitPriceCents: 1999,
    lineTotalCents: 1999,
    currency: "USD",
    statusLabel: "Processing",
    customerCancelAction: { id: "customer-cancel", label: "Cancel this item", requiresConfirmation: true },
    ...overrides,
  };
}

describe("CancellableOrderLine", () => {
  it("renders the exact same customer-visible output OrderLineItem alone would — proving genuine reuse", () => {
    const line = makeLine();
    const { container: wrapped } = render(<CancellableOrderLine line={line} onCancel={vi.fn()} />);
    const { container: plain } = render(<OrderLineItem line={line} />);

    expect(wrapped.textContent).toContain(plain.textContent);
  });

  it("renders the cancel button when customerCancelAction is present", () => {
    render(<CancellableOrderLine line={makeLine()} onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Cancel this item" })).toBeInTheDocument();
  });

  it("renders no cancel button when customerCancelAction is null (e.g. an STL line)", () => {
    render(<CancellableOrderLine line={makeLine({ customerCancelAction: null })} onCancel={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("confirming calls onCancel with the lineId and the action id", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<CancellableOrderLine line={makeLine({ id: "line-5" })} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Cancel this item" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onCancel).toHaveBeenCalledWith("line-5", "customer-cancel");
  });

  it("renders the caller-supplied errorMessage for this line", () => {
    render(
      <CancellableOrderLine
        line={makeLine()}
        errorMessage="This item can no longer be cancelled because fulfillment has progressed."
        onCancel={vi.fn()}
      />
    );
    expect(
      screen.getByText("This item can no longer be cancelled because fulfillment has progressed.")
    ).toBeInTheDocument();
  });

  it("two independent lines render independently — one line's state never affects another's", () => {
    render(
      <>
        <CancellableOrderLine line={makeLine({ id: "line-a" })} onCancel={vi.fn()} />
        <CancellableOrderLine line={makeLine({ id: "line-b", customerCancelAction: null })} onCancel={vi.fn()} />
      </>
    );
    expect(screen.getAllByRole("button", { name: "Cancel this item" })).toHaveLength(1);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CancellableOrderLine line={makeLine()} onCancel={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
