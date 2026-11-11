import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AdminPaymentView } from "./AdminPaymentView";
import { CreateChargeback } from "./CreateChargeback";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import { ADMIN_PAYMENT_MESSAGES } from "@/lib/admin/payments/adminPaymentPresentation";
import { paymentDetailDTO, paymentDTO } from "@/lib/admin/payments/adminPaymentFixtures";
import { adminDetailDTO, adminLineDTO, ADMIN_LINE_ID, ADMIN_ORDER_ID } from "@/lib/admin/orders/adminOrderFixtures";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const, status, code, message: "RAW", detail: "RAW DETAIL", raw: { status, code, detail: "RAW DETAIL", ...extra },
});

function wrap(node: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

const unpaid = paymentDTO({ status: "pending", verified_at: null });

describe("manual release (release_order)", () => {
  it("offered only with the server's release_order; reason >= 10; exact body", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "releaseOrder").mockResolvedValue({ order_id: "o", status: "cancelled", cancelled_at: "2026-11-12T00:00:00Z", attempts_expired: [], events_dismissed: [] });
    wrap(<AdminPaymentView detail={paymentDetailDTO({ payment: unpaid, available_actions: ["reconcile", "release_order"] })} />);
    await user.click(screen.getByRole("button", { name: "Release order" }));
    const dialog = screen.getByRole("dialog", { name: "Release this unpaid order?" });
    await user.type(within(dialog).getByLabelText("Reason"), "short");
    await user.click(within(dialog).getByRole("button", { name: "Release order" }));
    expect(within(dialog).getByText("Explain in at least 10 characters.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText("Reason"), " - customer never paid");
    await user.click(within(dialog).getByRole("button", { name: "Release order" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(paymentDetailDTO().order.id, { reason: "short - customer never paid", events_reviewed: false }));
    expect(await screen.findByText(/The order was released/)).toBeInTheDocument();
  });

  it("requires the events-reviewed tick when events are unprocessed; grace_not_elapsed names the date", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "releaseOrder").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "grace_not_elapsed", release_available_at: "2026-11-13T10:00:00Z" }));
    wrap(<AdminPaymentView detail={paymentDetailDTO({ payment: paymentDTO({ status: "pending", unprocessed_event_count: 2 }), available_actions: ["reconcile", "release_order"] })} />);
    await user.click(screen.getByRole("button", { name: "Release order" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Reason"), "Customer never paid at all");
    await user.click(within(dialog).getByRole("button", { name: "Release order" }));
    expect(within(dialog).getByText("Confirm you reviewed the provider events.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Release order" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ events_reviewed: true })));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This order can be released from 13 November 2026");
  });

  it("no release without the server's action (mock payment)", () => {
    wrap(<AdminPaymentView detail={paymentDetailDTO()} />);
    expect(screen.queryByRole("button", { name: "Release order" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record late capture" })).not.toBeInTheDocument();
  });
});

describe("record late capture", () => {
  it("offered with the confirm gate on an unpaid attempt; keyed; links the obligation", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "recordCapture").mockResolvedValue({ outcome: "recorded", payment: { id: "p", status: "expired" }, refund_id: "r-late" });
    wrap(<AdminPaymentView detail={paymentDetailDTO({ payment: paymentDTO({ status: "expired" }), available_actions: ["confirm"] })} />);
    await user.click(screen.getByRole("button", { name: "Record late capture" }));
    const dialog = screen.getByRole("dialog", { name: "Record a late capture?" });
    await user.type(within(dialog).getByLabelText(/Captured amount/), "30");
    await user.type(within(dialog).getByLabelText("Dashboard reference"), "DASH-9");
    await user.type(within(dialog).getByLabelText("Reason"), "Dashboard shows a capture");
    await user.click(within(dialog).getByRole("button", { name: "Record late capture" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const [, body, key] = spy.mock.calls[0]!;
    expect(body).toEqual({ captured_amount_cents: 3000, captured_currency: "USD", dashboard_reference: "DASH-9", reason: "Dashboard shows a capture" });
    expect(IDEMPOTENCY_KEY_PATTERN.test(key)).toBe(true);
    expect(await screen.findByRole("link", { name: "Open its refund obligation" })).toHaveAttribute("href", "/admin/refunds/r-late");
  });

  it("not offered once paid; use_confirm refusal is mapped", async () => {
    const user = userEvent.setup();
    const { unmount } = wrap(<AdminPaymentView detail={paymentDetailDTO({ available_actions: ["confirm"] })} />);
    expect(screen.queryByRole("button", { name: "Record late capture" })).not.toBeInTheDocument();
    unmount();
    vi.spyOn(adminPaymentsApi, "recordCapture").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "use_confirm" }));
    wrap(<AdminPaymentView detail={paymentDetailDTO({ payment: paymentDTO({ status: "failed" }), available_actions: ["confirm"] })} />);
    await user.click(screen.getByRole("button", { name: "Record late capture" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Captured amount/), "36");
    await user.type(within(dialog).getByLabelText("Dashboard reference"), "DASH-1");
    await user.type(within(dialog).getByLabelText("Reason"), "Matches the payment amount");
    await user.click(within(dialog).getByRole("button", { name: "Record late capture" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("use Confirm by hand instead");
  });
});

describe("CreateChargeback", () => {
  const paid = adminDetailDTO({
    payment_method: "online",
    payment_reached_paid: true,
    payment_due: false,
    amount_due: null,
    lines: [adminLineDTO({ fulfillment_status: "delivered", available_actions: [] })],
    payments: [{ id: "pay-1", provider: "mock", status: "paid", amount: { amount_cents: 3600, currency: "USD" }, initiated_at: "2026-11-10T10:00:00Z", verified_at: null, late_captured_at: null, recorded_by: null }],
  });

  it("not offered for a cash-only or unpaid order", () => {
    const { container } = wrap(<CreateChargeback order={adminDetailDTO()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("validates, sends the exact body with an aware received_at and a key", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "createChargeback").mockResolvedValue({} as never);
    wrap(<CreateChargeback order={paid} />);
    await user.click(screen.getByRole("button", { name: "Record a chargeback" }));
    const dialog = screen.getByRole("dialog", { name: "Record a chargeback?" });
    await user.click(within(dialog).getByRole("button", { name: "Record chargeback" }));
    expect(within(dialog).getByText("Enter the provider's dispute reference.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText("Provider dispute reference"), "DSP-1");
    await user.type(within(dialog).getByLabelText(/Amount charged back/), "36");
    await user.type(within(dialog).getByLabelText("Received at"), "2026-11-11T09:30");
    await user.type(within(dialog).getByLabelText("Reason"), "Customer disputed");
    await user.click(within(dialog).getByRole("button", { name: "Record chargeback" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const [orderId, body, key] = spy.mock.calls[0]!;
    expect(orderId).toBe(ADMIN_ORDER_ID);
    expect(body).toEqual({
      payment_id: "pay-1",
      provider_dispute_reference: "DSP-1",
      charged_cents: 3600,
      items: [],
      reason: "Customer disputed",
      received_at: new Date("2026-11-11T09:30").toISOString(),
    });
    expect(IDEMPOTENCY_KEY_PATTERN.test(key)).toBe(true);
  });

  it("CHARGEBACK_ALLOCATION_INVALID shows the server's chargeable amount and balances", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminPaymentsApi, "createChargeback").mockRejectedValue(
      http(422, "CHARGEBACK_ALLOCATION_INVALID", { available: { lines: [{ order_item_id: ADMIN_LINE_ID, balance_cents: 3600 }], payment_cents: 3600, chargeable_cents: 2000 } })
    );
    wrap(<CreateChargeback order={paid} />);
    await user.click(screen.getByRole("button", { name: "Record a chargeback" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Provider dispute reference"), "DSP-2");
    await user.type(within(dialog).getByLabelText(/Amount charged back/), "20");
    await user.type(within(dialog).getByLabelText("Received at"), "2026-11-11T09:30");
    await user.type(within(dialog).getByLabelText("Reason"), "Partial dispute");
    await user.type(within(dialog).getByLabelText(/^Articulated Dragon/), "5");
    await user.click(within(dialog).getByRole("button", { name: "Record chargeback" }));
    expect(await within(dialog).findByText(ADMIN_PAYMENT_MESSAGES.chargebackAllocation)).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Items must total\s*\$20\.00/);
    expect(within(dialog).getByLabelText(/Articulated Dragon \(up to \$36\.00\)/)).toBeInTheDocument();
  });
});
