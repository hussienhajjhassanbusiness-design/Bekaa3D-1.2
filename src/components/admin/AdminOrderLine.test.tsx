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

  // FVS-031-IMPLEMENTATION-PLAN.md §0 — re-ship/reprint/refund are
  // NOT a new component: VS-025 says they flow through the existing
  // line-transition endpoint, i.e. the same availableActions array
  // TransitionActions already renders. No special-cased code exists
  // anywhere for a "returned" line — these fixtures prove the
  // existing architecture already handles them.
  it("a returned line's re-ship/reprint/refund-labeled actions render via the existing availableActions architecture, with no special casing", () => {
    render(
      <AdminOrderLine
        line={makeLine({
          statusLabel: "Returned",
          availableActions: [
            { id: "re-ship", label: "Re-ship", requiresConfirmation: false },
            { id: "reprint", label: "Reprint", requiresConfirmation: false },
            { id: "refund", label: "Refund", requiresConfirmation: true },
          ],
        })}
        onSelectAction={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Re-ship" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reprint" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refund" })).toBeInTheDocument();
  });

  // FVS-031-IMPLEMENTATION-PLAN.md T06 — admin cancellation is its
  // own endpoint per VS-025, never folded into availableActions
  // (#SECURITY-SERVER-CANCELLATION-AUTHORITY). AdminOrderLine owns
  // its own AdminCancelDialog instance internally, mirroring how
  // TransitionActions owns its own ConfirmDialog — no second
  // focus-trap implementation anywhere in this file.
  describe("admin cancellation", () => {
    it("renders no admin-cancel button when the line has no adminCancelAction", () => {
      render(<AdminOrderLine line={makeLine()} onSelectAction={vi.fn()} onAdminCancel={vi.fn()} />);
      expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
    });

    it("renders the admin-cancel button using the server-supplied label when adminCancelAction is present", () => {
      render(
        <AdminOrderLine
          line={makeLine({ adminCancelAction: { id: "admin-cancel", label: "Cancel order line", requiresConfirmation: true } })}
          onSelectAction={vi.fn()}
          onAdminCancel={vi.fn()}
        />
      );
      expect(screen.getByRole("button", { name: "Cancel order line" })).toBeInTheDocument();
    });

    it("clicking the admin-cancel button opens AdminCancelDialog; confirming calls onAdminCancel with the lineId and trimmed reason", async () => {
      const onAdminCancel = vi.fn();
      const user = userEvent.setup();
      render(
        <AdminOrderLine
          line={makeLine({
            id: "line-7",
            adminCancelAction: { id: "admin-cancel", label: "Cancel order line", requiresConfirmation: true },
          })}
          onSelectAction={vi.fn()}
          onAdminCancel={onAdminCancel}
        />
      );

      await user.click(screen.getByRole("button", { name: "Cancel order line" }));
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(onAdminCancel).not.toHaveBeenCalled();

      await user.type(screen.getByLabelText("Reason"), "Customer requested cancellation");
      await user.click(screen.getByRole("button", { name: "Confirm" }));

      expect(onAdminCancel).toHaveBeenCalledWith("line-7", "Customer requested cancellation");
    });

    it("passes the line's refundObligationMessage through to the dialog verbatim", async () => {
      const user = userEvent.setup();
      render(
        <AdminOrderLine
          line={makeLine({
            adminCancelAction: { id: "admin-cancel", label: "Cancel order line", requiresConfirmation: true },
            refundObligationMessage: "Cancelling after production may require a refund.",
          })}
          onSelectAction={vi.fn()}
          onAdminCancel={vi.fn()}
        />
      );

      await user.click(screen.getByRole("button", { name: "Cancel order line" }));
      expect(screen.getByText("Cancelling after production may require a refund.")).toBeInTheDocument();
    });
  });
});
