import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderDetailView } from "./OrderDetailView";
import type { OrderPaymentControls } from "./OrderPaymentSection";
import type { RetryPaymentState } from "@/lib/orders/useRetryPayment";
import { PAYMENT_RETRY_MESSAGES } from "@/lib/orders/paymentRetryErrors";
import { adaptOrderDetail } from "@/lib/orders/orderModel";
import { detailDTO, lineDTO, pendingOnlineDetailDTO, stlLineDTO } from "@/lib/orders/orderFixtures";
import type { OrderDetailReadDTO } from "@/lib/orders/orderTypes";

function renderOrder(dto: OrderDetailReadDTO, pickup = { available: true, address: "Bekaa3D Workshop, Zahle", hours: "Mon-Fri 9-5" }) {
  render(<OrderDetailView order={adaptOrderDetail(dto)} pickup={pickup} />);
}

function controls(overrides: Partial<OrderPaymentControls> = {}, retryState: RetryPaymentState = { kind: "idle" }) {
  return {
    polling: false,
    timedOut: false,
    onCheckAgain: vi.fn(),
    onHoldElapsed: vi.fn(),
    retry: { state: retryState, onRetry: vi.fn(), onResume: vi.fn() },
    ...overrides,
  } satisfies OrderPaymentControls;
}

function renderWithControls(dto: OrderDetailReadDTO, c: OrderPaymentControls = controls()) {
  render(<OrderDetailView order={adaptOrderDetail(dto)} paymentControls={c} />);
  return c;
}

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const pay = (status: string) => ({ status, provider: "mock", amount: usd(2500) });

function section(name: string) {
  return screen.getByRole("region", { name });
}

describe("OrderDetailView", () => {
  it("shows the order number, status, placed date and a link back to the history", () => {
    renderOrder(detailDTO());
    expect(screen.getByRole("heading", { level: 1, name: "Order B3D-2026-000123" })).toBeInTheDocument();
    expect(screen.getAllByText("In progress").length).toBeGreaterThan(0);
    expect(screen.getByText(/placed 10 november 2026/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to your orders/i })).toHaveAttribute("href", "/account/orders");
  });

  describe("cash order", () => {
    it("shows the amount due as due, with no payment status and never 'Paid'", () => {
      renderOrder(detailDTO());
      const payment = section("Payment");
      expect(payment).toHaveTextContent("Cash");
      expect(payment).toHaveTextContent(/payment due in cash to the courier on delivery: \$25\.00/i);
      expect(payment).toHaveTextContent(/hasn't been paid yet/i);
      expect(within(payment).queryByText(/payment status/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/^paid$/i)).not.toBeInTheDocument();
      expect(section("Summary")).toHaveTextContent(/amount due\$25\.00/i);
    });

    it("shows the amount due exactly as given when it differs from the total", () => {
      renderOrder(detailDTO({ amount_due: { amount_cents: 1250, currency: "USD" } }));
      expect(section("Summary")).toHaveTextContent(/total\$25\.00/i);
      expect(section("Summary")).toHaveTextContent(/amount due\$12\.50/i);
    });

    it("says pay at pickup for a cash pickup order", () => {
      renderOrder(detailDTO({ fulfillment_method: "pickup", delivery_address: null, delivery_fee_note: null }));
      expect(section("Payment")).toHaveTextContent(/when you pick up your order/i);
    });

    it("labels a recorded cash payment from its own status", () => {
      renderOrder(
        detailDTO({
          payment_due: false,
          amount_due: null,
          status: "completed",
          payment: { status: "paid", provider: "cash", amount: { amount_cents: 2500, currency: "USD" } },
        })
      );
      expect(within(section("Payment")).getByText("Paid")).toBeInTheDocument();
      expect(section("Payment")).not.toHaveTextContent(/payment due/i);
    });
  });

  describe("online order", () => {
    it("shows a pending online order as awaiting payment, never paid, with its hold time", () => {
      renderOrder(pendingOnlineDetailDTO());
      const payment = section("Payment");
      expect(payment).toHaveTextContent("Online payment");
      expect(within(payment).getByText("Awaiting payment")).toBeInTheDocument();
      expect(payment).toHaveTextContent(/hasn't been confirmed as paid/i);
      expect(payment).toHaveTextContent(/may be released after 10 november 2026/i);
      expect(screen.queryByText(/^paid$/i)).not.toBeInTheDocument();
    });

    it("without the page's controls it is read-only: no retry, cancel, receipt, problem or redirect control", () => {
      renderOrder(pendingOnlineDetailDTO({ can_retry_payment: true, can_cancel: true }));
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /pay|retry|cancel|receipt|problem|continue/i })).not.toBeInTheDocument();
    });

    it("mounts no cancel / confirm receipt / report problem by itself: only the page's customerActions slot does (FVS-031)", () => {
      renderWithControls(pendingOnlineDetailDTO({ can_retry_payment: true, can_cancel: true }));
      expect(screen.queryByRole("button", { name: /cancel|receipt|problem/i })).not.toBeInTheDocument();
    });

    it("shows a paid online payment as Paid only because the server says so", () => {
      renderOrder(
        pendingOnlineDetailDTO({
          status: "in_progress",
          hold_expires_at: null,
          payment: { status: "paid", provider: "mock", amount: { amount_cents: 2500, currency: "USD" } },
        })
      );
      expect(within(section("Payment")).getByText("Paid")).toBeInTheDocument();
      expect(section("Payment")).not.toHaveTextContent(/hasn't been confirmed/i);
    });

    it("degrades an unknown payment status safely", () => {
      renderOrder(
        pendingOnlineDetailDTO({ payment: { status: "on_review", provider: "mock", amount: { amount_cents: 1, currency: "USD" } } })
      );
      expect(within(section("Payment")).getByText("Status unavailable")).toBeInTheDocument();
    });
  });

  describe("fulfillment", () => {
    it("shows the delivery snapshot, phone, estimated ready date and the courier-fee copy", () => {
      renderOrder(detailDTO());
      const delivery = section("Delivery");
      expect(delivery).toHaveTextContent("Rana Haddad");
      expect(delivery).toHaveTextContent("Main Street 12, Hoch el Oumara");
      expect(delivery).toHaveTextContent("Zahle, Bekaa");
      expect(delivery).toHaveTextContent("Blue gate");
      expect(delivery).toHaveTextContent("+96170123456");
      expect(delivery).toHaveTextContent(/estimated ready date: 14 november 2026/i);
      expect(section("Summary")).toHaveTextContent(/courier sets the delivery fee/i);
      // The server's own note text is not echoed.
      expect(screen.queryByText("The courier collects the delivery fee.")).not.toBeInTheDocument();
    });

    it("shows pickup with the current pickup location and no address or courier fee", () => {
      renderOrder(detailDTO({ fulfillment_method: "pickup", delivery_address: null, delivery_fee_note: null }));
      const pickup = section("Pickup");
      expect(pickup).toHaveTextContent(/collect this order from us/i);
      expect(pickup).toHaveTextContent("Bekaa3D Workshop, Zahle");
      expect(pickup).toHaveTextContent("+96170123456");
      expect(screen.queryByText(/courier sets the delivery fee/i)).not.toBeInTheDocument();
    });

    it("explains an STL-only order is emailed, not shipped", () => {
      renderOrder(
        pendingOnlineDetailDTO({
          fulfillment_method: null,
          delivery_address: null,
          contact_phone: null,
          delivery_fee_note: null,
          estimated_dispatch_at: null,
          lines: [stlLineDTO({ fulfillment_status: "pending" })],
        })
      );
      expect(section("Delivery")).toHaveTextContent(/nothing is shipped/i);
    });
  });

  describe("lines", () => {
    it("shows each physical line's snapshot", () => {
      renderOrder(detailDTO());
      const items = section("Items");
      expect(items).toHaveTextContent("Cedar Planter");
      expect(items).toHaveTextContent(/physical item · qty 2 × \$12\.50/i);
      expect(items).toHaveTextContent("$25.00");
      expect(items).toHaveTextContent("Received");
    });

    it("shows a paid STL line as not yet emailed and an emailed one with its date — never a download", () => {
      renderOrder(
        detailDTO({
          lines: [
            lineDTO(),
            stlLineDTO(),
            stlLineDTO({ id: "line-stl-2", name: "Castle STL", fulfillment_status: "delivered", fulfilled_at: "2026-11-11T12:00:00Z" }),
          ],
        })
      );
      const items = section("Items");
      expect(items).toHaveTextContent("Paid, not yet emailed");
      expect(items).toHaveTextContent("We'll email this file to you.");
      expect(items).toHaveTextContent("Emailed");
      expect(items).toHaveTextContent(/emailed to you on 11 november 2026/i);
      expect(items).not.toHaveTextContent(/download/i);
      expect(screen.queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    });

    it("says an STL on an unpaid online order is emailed once payment is confirmed", () => {
      renderOrder(pendingOnlineDetailDTO({ lines: [stlLineDTO({ fulfillment_status: "pending" })] }));
      expect(section("Items")).toHaveTextContent(/once your payment is confirmed/i);
    });

    it("shows receipt/problem/cancel timestamps read-only", () => {
      renderOrder(
        detailDTO({
          lines: [
            lineDTO({
              fulfillment_status: "delivered",
              receipt_confirmed_at: "2026-11-12T12:00:00Z",
              problem_reported_at: "2026-11-13T12:00:00Z",
            }),
            lineDTO({ id: "l2", fulfillment_status: "cancelled", cancelled_at: "2026-11-12T12:00:00Z" }),
          ],
        })
      );
      const items = section("Items");
      expect(items).toHaveTextContent(/you confirmed receipt on 12 november 2026/i);
      expect(items).toHaveTextContent(/you reported a problem on 13 november 2026/i);
      expect(items).toHaveTextContent(/cancelled on 12 november 2026/i);
    });

    it("degrades an unknown line status safely", () => {
      renderOrder(detailDTO({ lines: [lineDTO({ fulfillment_status: "lost_in_space" as never })] }));
      expect(section("Items")).toHaveTextContent("Status unavailable");
    });
  });

  it("shows totals from the server", () => {
    renderOrder(detailDTO({ subtotal: { amount_cents: 2400, currency: "USD" }, tax: { amount_cents: 100, currency: "USD" } }));
    const summary = section("Summary");
    expect(summary).toHaveTextContent(/subtotal\$24\.00/i);
    expect(summary).toHaveTextContent(/tax\$1\.00/i);
    expect(summary).toHaveTextContent(/total\$25\.00/i);
  });

  it("shows the customer note and the status history with line names", () => {
    renderOrder(
      detailDTO({
        lines: [stlLineDTO()],
        status_history: [
          { order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-10T09:30:00Z" },
          { order_item_id: "line-stl-1", from_status: "pending", to_status: "delivered", at: "2026-11-11T12:00:00Z" },
        ],
      })
    );
    expect(section("Your note")).toHaveTextContent("Please call before delivery");
    const updates = section("Order updates");
    expect(updates).toHaveTextContent("Order: In progress");
    expect(updates).toHaveTextContent("Dragon STL: Emailed");
  });

  it("lists refunds when present, and no refunds section otherwise", () => {
    renderOrder(detailDTO());
    expect(screen.queryByRole("region", { name: "Refunds" })).not.toBeInTheDocument();
    renderOrder(
      detailDTO({
        refunds: [{ kind: "cancellation", status: "processing", amount: { amount_cents: 1250, currency: "USD" }, created_at: "2026-11-11T12:00:00Z" }],
      })
    );
    expect(section("Refunds")).toHaveTextContent(/cancellation refund · processing/i);
    expect(section("Refunds")).toHaveTextContent("$12.50");
  });

  describe("payment states (FVS-027)", () => {
    it("processing: being processed, not paid", () => {
      renderWithControls(pendingOnlineDetailDTO({ payment: pay("processing") }));
      const payment = section("Payment");
      expect(within(payment).getByText("Payment processing")).toBeInTheDocument();
      expect(payment).toHaveTextContent(/being processed/i);
      expect(payment).not.toHaveTextContent(/payment has been confirmed/i);
    });

    it("failed on a payable order: says so and offers Retry payment when the server allows", async () => {
      const c = renderWithControls(pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }));
      const payment = section("Payment");
      expect(within(payment).getByText("Payment failed")).toBeInTheDocument();
      expect(payment).toHaveTextContent(/last payment attempt didn't go through/i);
      await userEvent.setup().click(within(payment).getByRole("button", { name: "Retry payment" }));
      expect(c.retry.onRetry).toHaveBeenCalledTimes(1);
    });

    it("expired on a payable order: says so", () => {
      renderWithControls(pendingOnlineDetailDTO({ payment: pay("expired"), can_retry_payment: true }));
      expect(within(section("Payment")).getByText("Payment expired")).toBeInTheDocument();
      expect(section("Payment")).toHaveTextContent(/expired before it was completed/i);
    });

    it("failed on a released (cancelled) order: no retry, no countdown, no polling copy", () => {
      renderWithControls(
        pendingOnlineDetailDTO({ status: "cancelled", cancelled_at: "2026-11-10T10:40:00Z", hold_expires_at: null, payment: pay("failed") }),
        controls({ polling: true })
      );
      const payment = section("Payment");
      expect(payment).toHaveTextContent("This payment didn't go through.");
      expect(within(payment).queryByRole("button")).not.toBeInTheDocument();
      expect(payment).not.toHaveTextContent(/time left|checking/i);
    });

    it("paid: confirmed only from the server's status", () => {
      renderWithControls(pendingOnlineDetailDTO({ status: "in_progress", hold_expires_at: null, payment: pay("paid") }));
      expect(section("Payment")).toHaveTextContent("Your payment has been confirmed.");
      expect(within(section("Payment")).queryByRole("button")).not.toBeInTheDocument();
    });

    it("refunded is presented without any refund action", () => {
      renderWithControls(pendingOnlineDetailDTO({ status: "refunded", hold_expires_at: null, payment: pay("refunded") }));
      expect(within(section("Payment")).getByText("Refunded")).toBeInTheDocument();
      expect(section("Payment")).toHaveTextContent("This payment has been refunded.");
      expect(screen.queryByRole("button", { name: /refund/i })).not.toBeInTheDocument();
    });

    it("partially refunded", () => {
      renderWithControls(
        pendingOnlineDetailDTO({
          status: "partially_refunded",
          hold_expires_at: null,
          payment: pay("partially_refunded"),
          refunds: [{ kind: "admin", status: "refunded", amount: usd(500), created_at: "2026-11-11T12:00:00Z" }],
        })
      );
      expect(within(section("Payment")).getByText("Partially refunded")).toBeInTheDocument();
      expect(section("Payment")).toHaveTextContent("Part of this payment has been refunded.");
      expect(section("Refunds")).toHaveTextContent("$5.00");
    });

    it("an unknown future status: 'Status unavailable', never the raw value", () => {
      renderWithControls(pendingOnlineDetailDTO({ payment: pay("held_for_review") }));
      expect(within(section("Payment")).getByText("Status unavailable")).toBeInTheDocument();
      expect(screen.queryByText(/held_for_review/)).not.toBeInTheDocument();
    });

    it("pending with a hold: shows the countdown", () => {
      renderWithControls(pendingOnlineDetailDTO({ hold_expires_at: "2999-01-01T00:00:00Z" }));
      expect(section("Payment")).toHaveTextContent(/time left to complete payment/i);
    });

    it("no retry button while can_retry_payment is false (e.g. a live attempt)", () => {
      renderWithControls(pendingOnlineDetailDTO({ can_retry_payment: false }));
      expect(screen.queryByRole("button", { name: /retry payment/i })).not.toBeInTheDocument();
    });

    it("the retry button is disabled while sending and while leaving for the provider", () => {
      const { unmount } = render(
        <OrderDetailView
          order={adaptOrderDetail(pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }))}
          paymentControls={controls({}, { kind: "sending" })}
        />
      );
      expect(screen.getByRole("button", { name: "Starting payment…" })).toBeDisabled();
      unmount();
      renderWithControls(pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }), controls({}, { kind: "redirecting" }));
      expect(screen.getByRole("button", { name: "Opening payment page…" })).toBeDisabled();
    });

    it("an uncertain outcome says a resend is safe and relabels the button", () => {
      renderWithControls(
        pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }),
        controls({}, {
          kind: "error",
          outcome: { kind: "uncertain", message: PAYMENT_RETRY_MESSAGES.uncertain, uncertain: true, refetchOrder: false, resumeUrl: null },
        })
      );
      expect(screen.getByRole("alert")).toHaveTextContent(PAYMENT_RETRY_MESSAGES.uncertain);
      expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    });

    it("a refusal stays visible after the server withdraws can_retry_payment", () => {
      renderWithControls(
        pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: false }),
        controls({}, {
          kind: "error",
          outcome: { kind: "not-retryable", message: PAYMENT_RETRY_MESSAGES.holdExpired, uncertain: false, refetchOrder: true, resumeUrl: null },
        })
      );
      expect(screen.getByRole("alert")).toHaveTextContent(PAYMENT_RETRY_MESSAGES.holdExpired);
      expect(screen.queryByRole("button", { name: /retry payment/i })).not.toBeInTheDocument();
    });

    it("PAYMENT_ALREADY_ACTIVE offers Continue to payment with the server's URL", async () => {
      const url = "https://pay.example.test/s/1";
      const c = renderWithControls(
        pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }),
        controls({}, {
          kind: "error",
          outcome: { kind: "already-active", message: PAYMENT_RETRY_MESSAGES.alreadyActiveResume, uncertain: false, refetchOrder: true, resumeUrl: url },
        })
      );
      await userEvent.setup().click(screen.getByRole("button", { name: "Continue to payment" }));
      expect(c.retry.onResume).toHaveBeenCalledWith(url);
    });

    it("session expiry during retry links to sign-in back to this order", () => {
      renderWithControls(
        pendingOnlineDetailDTO({ payment: pay("failed"), can_retry_payment: true }),
        controls({}, {
          kind: "error",
          outcome: { kind: "session-expired", message: PAYMENT_RETRY_MESSAGES.sessionExpired, uncertain: false, refetchOrder: false, resumeUrl: null },
        })
      );
      expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
        "href",
        `/login?returnTo=${encodeURIComponent("/account/orders/0b6f2a52-7f5d-4f3e-9c55-3b8b1f5d2a10")}`
      );
    });

    it("cash: no retry, countdown, polling or redirect even with stray flags and controls", () => {
      renderWithControls(
        detailDTO({ can_retry_payment: true, hold_expires_at: "2999-01-01T00:00:00Z", status: "pending_payment" }),
        controls({ polling: true, timedOut: true }, { kind: "started" })
      );
      const payment = section("Payment");
      expect(within(payment).queryByRole("button")).not.toBeInTheDocument();
      expect(payment).not.toHaveTextContent(/time left|checking|confirmation|new payment/i);
    });
  });

  // Batch 7 (DERIVED detail layout): structure the redesign relies on.
  describe("layout (Batch 7)", () => {
    it("has one h1 with the status pill in the same parent and h2 sections in a task-first order", () => {
      renderOrder(
        detailDTO({
          refunds: [{ kind: "cancellation", status: "processing", amount: usd(1250), created_at: "2026-11-12T10:00:00Z" }],
        } as Partial<OrderDetailReadDTO>)
      );
      const h1 = screen.getByRole("heading", { level: 1 });
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      expect(h1.parentElement).toHaveTextContent("In progress");
      const h2s = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
      expect(h2s).toEqual(["Payment", "Summary", "Refunds", "Items", "Delivery", "Your note", "Order updates"]);
    });

    it("lists status history as an ordered list with readable entries", () => {
      renderOrder(
        detailDTO({
          lines: [lineDTO(), stlLineDTO()],
          status_history: [
            { order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-10T09:30:00Z" },
            { order_item_id: null, from_status: "in_progress", to_status: "completed", at: "2026-11-11T09:30:00Z" },
          ],
        })
      );
      const list = within(section("Order updates")).getByRole("list");
      expect(list.tagName).toBe("OL");
      const entries = within(list).getAllByRole("listitem").map((li) => li.textContent ?? "");
      expect(entries[0]).toContain("Order: In progress");
      expect(entries[1]).toContain("Order: Completed");
    });

    it("shows a pending online order's countdown as plain text, not as a live status", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-11-10T09:50:00Z"));
      renderWithControls(pendingOnlineDetailDTO());
      const countdown = screen.getByText(/time left to complete payment/i);
      expect(countdown.closest("[role=status],[aria-live]")).toBeNull();
      expect(screen.queryByRole("status")).toBeNull();
      vi.useRealTimers();
    });
  });
});
