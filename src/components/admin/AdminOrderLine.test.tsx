import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminOrderLine } from "./AdminOrderLine";
import { OrderLineItem } from "@/components/account/OrderLineItem";
import type { AdminOrderLineModel } from "@/lib/admin/adminOrderModel";

// FVS-030-IMPLEMENTATION-PLAN.md T05 — composes FVS-029's
// OrderLineItem (reused completely unmodified) alongside
// TransitionActions rendered separately, never injecting admin state
// into OrderLineItem itself (#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY).

function makeLine(overrides: Partial<AdminOrderLineModel> = {}): AdminOrderLineModel {
  return {
    id: "line-1",
    productDisplayName: "Garden Gnome",
    productType: "physical",
    quantity: 1,
    unitPriceCents: 1999,
    lineTotalCents: 1999,
    currency: "USD",
    statusLabel: "Processing",
    availableActions: [{ id: "move-to-production", label: "Move to production", requiresConfirmation: false }],
    ...overrides,
  };
}

describe("AdminOrderLine", () => {
  it("renders the exact same customer-visible output OrderLineItem alone would — proving genuine reuse", () => {
    const line = makeLine();
    const { container: adminContainer } = render(
      <AdminOrderLine line={line} onSelectAction={vi.fn()} />
    );
    const { container: plainContainer } = render(<OrderLineItem line={line} />);

    expect(adminContainer.textContent).toContain(plainContainer.textContent);
  });

  it("renders TransitionActions for the line's own availableActions", () => {
    render(<AdminOrderLine line={makeLine()} onSelectAction={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Move to production" })).toBeInTheDocument();
  });

  it("selecting an action calls the composed callback with (lineId, actionId)", async () => {
    const onSelectAction = vi.fn();
    const user = userEvent.setup();
    render(<AdminOrderLine line={makeLine({ id: "line-9" })} onSelectAction={onSelectAction} />);

    await user.click(screen.getByRole("button", { name: "Move to production" }));

    expect(onSelectAction).toHaveBeenCalledWith("line-9", "move-to-production");
  });

  it("a digital/STL line with availableActions: [] renders no transition controls at all, with no special-cased product-type check", () => {
    render(
      <AdminOrderLine
        line={makeLine({ productType: "stl", productDisplayName: "Dragon STL", availableActions: [] })}
        onSelectAction={vi.fn()}
      />
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AdminOrderLine line={makeLine()} onSelectAction={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
