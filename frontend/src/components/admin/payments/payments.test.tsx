import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AdminPaymentView } from "./AdminPaymentView";
import { CreateRefund } from "./CreateRefund";
import { RefundView } from "./RefundView";
import { adminPaymentsApi } from "@/lib/admin/payments/adminPaymentsApi";
import { ADMIN_PAYMENT_MESSAGES } from "@/lib/admin/payments/adminPaymentPresentation";
import { paymentDetailDTO, paymentDTO, refundDTO } from "@/lib/admin/payments/adminPaymentFixtures";
import { adminDetailDTO, adminLineDTO, ADMIN_LINE_ID, ADMIN_ORDER_ID } from "@/lib/admin/orders/adminOrderFixtures";
import { IDEMPOTENCY_KEY_PATTERN } from "@/lib/checkout/checkoutIdempotency";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW",
  detail: "RAW DETAIL",
  raw: { status, code, detail: "RAW DETAIL", ...extra },
});

function wrap(node: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
});

const paidOrder = adminDetailDTO({
  payment_method: "online",
  payment_reached_paid: true,
  payment_due: false,
  amount_due: null,
  lines: [adminLineDTO({ fulfillment_status: "delivered", available_actions: [] }), adminLineDTO({ id: "l-stl", name: "Dragon STL", product_type: "stl", fulfillment_status: "delivered", line_total: { amount_cents: 900, currency: "USD" }, available_actions: [] })],
  refund_balance: { lines: [{ order_item_id: ADMIN_LINE_ID, balance_cents: 3600 }, { order_item_id: "l-stl", balance_cents: 900 }], payment_cents: 4500 },
});

describe("CreateRefund", () => {
  it("not offered before payment or with nothing left", () => {
    const { container } = wrap(<CreateRefund order={adminDetailDTO()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("per-line amounts against the server's balances; exact body; one valid key; opens the refund", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "createRefund").mockResolvedValue(refundDTO({ id: "r-9" }));
    wrap(<CreateRefund order={paidOrder} />);
    await user.click(screen.getByRole("button", { name: "Record a refund" }));
    const dialog = screen.getByRole("dialog", { name: "Record a refund?" });
    expect(dialog).toHaveTextContent(/Left to refund on the payment:\s*\$45\.00/);
    await user.click(within(dialog).getByRole("button", { name: "Record refund" }));
    expect(within(dialog).getByText("Enter an amount for at least one item.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/Dragon STL \(up to \$9\.00\)/), "10");
    await user.type(within(dialog).getByLabelText("Reason"), "Corrupted file");
    await user.click(within(dialog).getByRole("button", { name: "Record refund" }));
    expect(within(dialog).getByText("More than this item's refundable balance.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
    const stl = within(dialog).getByLabelText(/Dragon STL/);
    await user.clear(stl);
    await user.type(stl, "9");
    await user.click(within(dialog).getByRole("button", { name: "Record refund" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const [orderId, body, key] = spy.mock.calls[0]!;
    expect(orderId).toBe(ADMIN_ORDER_ID);
    expect(body).toEqual({ items: [{ order_item_id: "l-stl", amount_cents: 900 }], reason: "Corrupted file" });
    expect(IDEMPOTENCY_KEY_PATTERN.test(key)).toBe(true);
    expect(push).toHaveBeenCalledWith("/admin/refunds/r-9");
  });

  it("an uncertain outcome resends with the SAME key; REFUND_EXCEEDS_AVAILABLE shows the server's balances", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn(adminPaymentsApi, "createRefund")
      .mockRejectedValueOnce({ kind: "timeout", message: "x", raw: null })
      .mockRejectedValueOnce(http(422, "REFUND_EXCEEDS_AVAILABLE", { available: { lines: [{ order_item_id: ADMIN_LINE_ID, balance_cents: 1000 }], payment_cents: 1000 } }));
    wrap(<CreateRefund order={paidOrder} />);
    await user.click(screen.getByRole("button", { name: "Record a refund" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Articulated Dragon/), "20");
    await user.type(within(dialog).getByLabelText("Reason"), "Late");
    await user.click(within(dialog).getByRole("button", { name: "Record refund" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(ADMIN_PAYMENT_MESSAGES.uncertain);
    await user.click(within(dialog).getByRole("button", { name: "Record refund" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(spy.mock.calls[1]![2]).toBe(spy.mock.calls[0]![2]);
    expect(await within(dialog).findByText(ADMIN_PAYMENT_MESSAGES.exceeds)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Articulated Dragon \(up to \$10\.00\)/)).toBeInTheDocument();
  });
});

describe("RefundView", () => {
  it("pending: settle / fail / void; settle sends only filled fields", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "settleRefund").mockResolvedValue(refundDTO({ status: "settled" }));
    wrap(<RefundView refund={refundDTO()} />);
    const actions = screen.getByRole("region", { name: "Refund actions" });
    expect(within(actions).getAllByRole("button").map((b) => b.textContent)).toEqual(["Mark settled", "Mark failed", "Void refund"]);
    await user.click(within(actions).getByRole("button", { name: "Mark settled" }));
    const dialog = screen.getByRole("dialog", { name: "Mark this refund settled?" });
    await user.type(within(dialog).getByLabelText(/Settlement reference/), "DASH-77");
    await user.click(within(dialog).getByRole("button", { name: "Mark settled" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("r-1", { reference: "DASH-77" }));
  });

  it("fail requires a reason; a 409 already_settled shows safe copy", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "failRefund").mockRejectedValue(http(409, "INVALID_STATE_TRANSITION", { reason: "already_settled" }));
    wrap(<RefundView refund={refundDTO()} />);
    await user.click(screen.getByRole("button", { name: "Mark failed" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Mark failed" }));
    expect(within(dialog).getByText("Enter a reason.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText("Reason"), "Card closed");
    await user.click(within(dialog).getByRole("button", { name: "Mark failed" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already settled");
    expect(dialog).not.toHaveTextContent("RAW");
  });

  it("failed and owed: reissue with a valid key, or void; settled: nothing", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "reissueRefund").mockResolvedValue(refundDTO({ id: "r-2" }));
    const { unmount } = wrap(<RefundView refund={refundDTO({ status: "failed", owed: true })} />);
    await user.click(screen.getByRole("button", { name: "Reissue refund" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reissue refund" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(IDEMPOTENCY_KEY_PATTERN.test(spy.mock.calls[0]![1])).toBe(true);
    unmount();
    wrap(<RefundView refund={refundDTO({ status: "settled", settled_at: "2026-11-11T12:00:00Z" })} />);
    expect(screen.queryByRole("region", { name: "Refund actions" })).not.toBeInTheDocument();
  });
});

describe("AdminPaymentView", () => {
  it("shows the payment and order; history and events without backend text or data", () => {
    wrap(
      <AdminPaymentView
        detail={paymentDetailDTO({
          events: [{ id: "e-2", event_type: "payment.failed", signature_valid: true, received_at: "2026-11-10T10:01:00Z", processed_at: null, processing_error: "RAW BACKEND TRACE" }],
        })}
      />
    );
    expect(screen.getByRole("heading", { level: 1, name: "Payment for order B3D-R1" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Payment" })).toHaveTextContent("Online (mock provider)");
    expect(screen.getByRole("region", { name: "Provider events" })).toHaveTextContent("Processing failed");
    expect(screen.getByRole("region", { name: "History" })).toHaveTextContent("Verified as paid");
    expect(document.body).not.toHaveTextContent(/RAW/);
  });

  it("reconcile: exactly the server's actions; 202 shows a queued notice; cash has none", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "reconcilePayment").mockResolvedValue({ payment: paymentDTO(), reconcile: "queued" });
    const { unmount } = wrap(<AdminPaymentView detail={paymentDetailDTO()} />);
    expect(screen.queryByRole("button", { name: "Confirm by hand" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check with provider" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Check with provider" }));
    expect(await screen.findByText(/Check requested/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith(paymentDTO().id);
    unmount();
    wrap(<AdminPaymentView detail={paymentDetailDTO({ payment: paymentDTO({ provider: "cash" }), available_actions: [] })} />);
    expect(screen.queryByRole("region", { name: "Payment actions" })).not.toBeInTheDocument();
  });

  it("confirm (provider without a status API): validates and sends the exact body", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminPaymentsApi, "confirmPayment").mockRejectedValue(http(422, "PAYMENT_AMOUNT_MISMATCH", { expected_amount_cents: 3600, currency: "USD" }));
    wrap(<AdminPaymentView detail={paymentDetailDTO({ available_actions: ["confirm"] })} />);
    await user.click(screen.getByRole("button", { name: "Confirm by hand" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Confirm payment" }));
    expect(within(dialog).getByText("Explain in at least 10 characters.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Provider reference"), "PROV-1");
    await user.type(within(dialog).getByLabelText(/Amount the provider shows/), "35");
    await user.type(within(dialog).getByLabelText("Reason"), "Seen in dashboard");
    await user.click(within(dialog).getByRole("button", { name: "Confirm payment" }));
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(paymentDTO().id, { provider_reference: "PROV-1", verified_amount_cents: 3500, verified_currency: "USD", reason: "Seen in dashboard" })
    );
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(ADMIN_PAYMENT_MESSAGES.amountMismatch);
  });
});
