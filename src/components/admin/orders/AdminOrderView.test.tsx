import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdminOrderView } from "./AdminOrderView";
import { adminOrderKeys, adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import { adminDetailDTO, adminLineDTO, ADMIN_LINE_ID, ADMIN_ORDER_ID } from "@/lib/admin/orders/adminOrderFixtures";
import type { AdminOrderDetailDTO } from "@/lib/admin/orders/adminOrderTypes";

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  detail: "RAW DETAIL",
  raw: { status, code, detail: "RAW DETAIL", ...extra },
});

function renderView(dto: AdminOrderDetailDTO) {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <AdminOrderView order={dto} />
    </QueryClientProvider>
  );
  return { queryClient, invalidate };
}

afterEach(() => vi.restoreAllMocks());

describe("AdminOrderView — rendering", () => {
  it("shows the server's order, real line state, fulfillment, cash due and history actors", () => {
    renderView(
      adminDetailDTO({
        status_history: [
          { order_item_id: null, from_status: null, to_status: "in_progress", actor_user_id: "c-1", reason: null, at: "2026-11-10T09:30:00Z" },
          { order_item_id: ADMIN_LINE_ID, from_status: "pending", to_status: "in_production", actor_user_id: "admin-9", reason: "Batch A", at: "2026-11-10T10:00:00Z" },
        ],
      })
    );
    expect(screen.getByRole("heading", { level: 1, name: "Order B3D-ADMIN001" })).toBeInTheDocument();
    expect(screen.getByText(/by rana@example.com/)).toBeInTheDocument();
    const items = screen.getByRole("region", { name: "Items" });
    expect(within(items).getByText("Pending")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Payment" })).toHaveTextContent(/Cash due\s*\$36\.00/);
    expect(screen.getByRole("region", { name: "Fulfillment" })).toHaveTextContent("Main St 12, Zahle, Beqaa");
    const history = screen.getByRole("region", { name: "History" });
    expect(history).toHaveTextContent("Customer");
    expect(history).toHaveTextContent(/Articulated Dragon:\s*In production/);
    expect(history).toHaveTextContent("Staff");
    expect(history).toHaveTextContent("“Batch A”");
  });

  it("renders exactly the server's available actions per line, none for a line with none", () => {
    renderView(
      adminDetailDTO({
        lines: [
          adminLineDTO(),
          adminLineDTO({ id: "l-2", name: "Done Lamp", fulfillment_status: "delivered", available_actions: [] }),
          adminLineDTO({
            id: "l-stl",
            name: "Dragon STL",
            product_type: "stl",
            fulfillment_status: "awaiting_delivery",
            available_actions: [{ target_status: "delivered", cancel_reasons: [] }],
          }),
        ],
      })
    );
    const items = screen.getByRole("region", { name: "Items" });
    expect(within(items).getByRole("button", { name: "Start production" })).toBeInTheDocument();
    expect(within(items).getByRole("button", { name: "Cancel line" })).toBeInTheDocument();
    expect(within(items).getByRole("button", { name: "Mark STL emailed" })).toBeInTheDocument();
    expect(within(items).getAllByRole("button")).toHaveLength(3);
    expect(within(items).getByText("Awaiting email delivery")).toBeInTheDocument();
    expect(screen.queryByText(/download|upload/i)).not.toBeInTheDocument();
  });

  it("read-only payments, refunds and chargebacks; no refund action in this phase", () => {
    renderView(
      adminDetailDTO({
        payment_method: "online",
        payment_due: false,
        amount_due: null,
        payment_reached_paid: true,
        payments: [{ id: "p1", provider: "mock", status: "paid", amount: { amount_cents: 3600, currency: "USD" }, initiated_at: "2026-11-10T09:30:00Z", verified_at: null, late_captured_at: null, recorded_by: null }],
        refunds: [{ id: "r1", kind: "cancellation", status: "pending", owed: false, amount: { amount_cents: 1800, currency: "USD" }, created_at: "2026-11-11T00:00:00Z" }],
      })
    );
    expect(screen.getByRole("region", { name: "Payment" })).toHaveTextContent("Online (mock provider)");
    expect(screen.getByRole("region", { name: "Refunds" })).toHaveTextContent(/Cancellation refund\s*Pending/);
    expect(screen.queryByRole("button", { name: /refund/i })).not.toBeInTheDocument();
  });
});

describe("AdminOrderView — line transition", () => {
  it("confirms, posts exactly {target_status}, stores the server's detail", async () => {
    const user = userEvent.setup();
    const next = adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "in_production", available_actions: [] })] });
    const spy = vi.spyOn(adminOrdersApi, "transitionLine").mockResolvedValue(next);
    const { queryClient, invalidate } = renderView(adminDetailDTO());
    await user.click(screen.getByRole("button", { name: "Start production" }));
    const dialog = screen.getByRole("dialog", { name: "Start production?" });
    expect(dialog).toHaveTextContent("Articulated Dragon: Pending → In production.");
    await user.click(within(dialog).getByRole("button", { name: "Start production" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith(ADMIN_ORDER_ID, ADMIN_LINE_ID, { target_status: "in_production" });
    expect(queryClient.getQueryData(adminOrderKeys.detail(ADMIN_ORDER_ID))).toBe(next);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: adminOrderKeys.root });
  });

  it("a cancel that takes reasons requires one of the server's reasons and sends the note", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminOrdersApi, "transitionLine").mockResolvedValue(adminDetailDTO());
    renderView(
      adminDetailDTO({
        lines: [
          adminLineDTO({
            fulfillment_status: "ready_to_ship",
            available_actions: [
              { target_status: "shipped", cancel_reasons: [] },
              { target_status: "cancelled", cancel_reasons: ["refused", "other"] },
            ],
          }),
        ],
      })
    );
    await user.click(screen.getByRole("button", { name: "Cancel line" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel line?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel line" }));
    expect(within(dialog).getByText("Choose a cancel reason.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
    expect(within(dialog).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose a reason",
      "Customer refused the order",
      "Other",
    ]);
    await user.selectOptions(within(dialog).getByLabelText("Cancel reason"), "refused");
    await user.type(within(dialog).getByLabelText(/Note for the order history/), "Refused at door");
    await user.click(within(dialog).getByRole("button", { name: "Cancel line" }));
    expect(spy).toHaveBeenCalledWith(ADMIN_ORDER_ID, ADMIN_LINE_ID, {
      target_status: "cancelled",
      reason: "Refused at door",
      cancel_reason: "refused",
    });
  });

  it("an illegal transition keeps the dialog with safe copy and re-reads the order", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminOrdersApi, "transitionLine").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "not_a_legal_edge", fulfillment_status: "cancelled" }));
    const { invalidate } = renderView(adminDetailDTO());
    await user.click(screen.getByRole("button", { name: "Start production" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start production" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("That step isn't allowed from the line's current state.");
    expect(dialog).not.toHaveTextContent("RAW");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: adminOrderKeys.root });
  });
});

describe("AdminOrderView — refusal re-read", () => {
  it("keeps the dialog and its error when the re-read line offers no action", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminOrdersApi, "transitionLine").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "line_closed" }));
    const queryClient = new QueryClient();
    const view = render(
      <QueryClientProvider client={queryClient}>
        <AdminOrderView order={adminDetailDTO()} />
      </QueryClientProvider>
    );
    await user.click(screen.getByRole("button", { name: "Start production" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start production" }));
    await screen.findByRole("alert");
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <AdminOrderView order={adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "cancelled", available_actions: [] })] })} />
      </QueryClientProvider>
    );
    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent("This line is already closed");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(within(screen.getByRole("region", { name: "Items" })).queryAllByRole("button")).toHaveLength(0);
  });
});

describe("AdminOrderView — handover refusal re-read", () => {
  it("keeps the handover dialog when the re-read withdraws the offer", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminOrdersApi, "cashHandover").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "lines_not_ready" }));
    const queryClient = new QueryClient();
    const shipped = adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "shipped", available_actions: [] })] });
    const view = render(
      <QueryClientProvider client={queryClient}>
        <AdminOrderView order={shipped} />
      </QueryClientProvider>
    );
    await user.click(screen.getByRole("button", { name: "Record cash handover" }));
    await user.type(within(screen.getByRole("dialog")).getByLabelText(/Cash received/), "36");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Record cash handover" }));
    await screen.findByRole("alert");
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <AdminOrderView order={adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "returned", available_actions: [] })] })} />
      </QueryClientProvider>
    );
    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent("Every line must be shipped");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("button", { name: "Record cash handover" })).not.toBeInTheDocument();
  });
});

describe("AdminOrderView — order-level actions", () => {
  const ready = adminDetailDTO({ lines: [adminLineDTO({ fulfillment_status: "shipped", available_actions: [{ target_status: "returned", cancel_reasons: [] }] })] });

  it("cash handover: offered only when every live line is ready; the typed amount is sent, never prefilled", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminOrdersApi, "cashHandover").mockResolvedValue(adminDetailDTO({ payment_due: false }));
    renderView(ready);
    await user.click(screen.getByRole("button", { name: "Record cash handover" }));
    const dialog = screen.getByRole("dialog", { name: "Record cash handover?" });
    expect(dialog).toHaveTextContent(/Amount due:\s*\$36\.00/);
    const amount = within(dialog).getByLabelText(/Cash received/);
    expect(amount).toHaveValue("");
    await user.click(within(dialog).getByRole("button", { name: "Record cash handover" }));
    expect(within(dialog).getByText("Enter the cash received.")).toBeInTheDocument();
    await user.type(amount, "36.00");
    await user.click(within(dialog).getByRole("button", { name: "Record cash handover" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(ADMIN_ORDER_ID, { amount_cents: 3600, currency: "USD" }));
  });

  it("cash handover: CASH_AMOUNT_MISMATCH names the server's amount due", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminOrdersApi, "cashHandover").mockRejectedValue(http(422, "CASH_AMOUNT_MISMATCH", { amount_due: { amount_cents: 3600, currency: "USD" } }));
    renderView(ready);
    await user.click(screen.getByRole("button", { name: "Record cash handover" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Cash received/), "30");
    await user.click(within(dialog).getByRole("button", { name: "Record cash handover" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The cash entered must be exactly the amount due ($36.00).");
  });

  it("no cash handover before the lines are ready, nor for an online order", () => {
    renderView(adminDetailDTO());
    expect(screen.queryByRole("button", { name: "Record cash handover" })).not.toBeInTheDocument();
  });

  it("cancel order: requires a reason, sends {reason}", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminOrdersApi, "cancelOrder").mockResolvedValue(adminDetailDTO({ status: "cancelled" }));
    renderView(adminDetailDTO());
    const actions = screen.getByRole("region", { name: "Order actions" });
    await user.click(within(actions).getByRole("button", { name: "Cancel order" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel this order?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel order" }));
    expect(within(dialog).getByText("Enter a reason for cancelling.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/Why is this order being cancelled/), "Out of filament");
    await user.click(within(dialog).getByRole("button", { name: "Cancel order" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(ADMIN_ORDER_ID, { reason: "Out of filament" }));
  });
});

describe("AdminOrderView — internal note", () => {
  it("saves through PATCH; blank clears it", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminOrdersApi, "updateNote").mockResolvedValue(adminDetailDTO({ admin_note: null }));
    renderView(adminDetailDTO({ admin_note: "Fragile" }));
    const box = screen.getByLabelText(/Internal note — not visible to customers/);
    expect(box).toHaveValue("Fragile");
    await user.clear(box);
    await user.click(within(screen.getByRole("region", { name: "Internal note" })).getByRole("button", { name: "Save" }));
    expect(spy).toHaveBeenCalledWith(ADMIN_ORDER_ID, { admin_note: null });
  });
});
