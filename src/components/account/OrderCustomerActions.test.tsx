import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OrderCustomerActions } from "./OrderCustomerActions";
import { ordersApi } from "@/lib/orders/ordersApi";
import { orderKeys } from "@/lib/orders/orderKeys";
import { adaptOrderDetail } from "@/lib/orders/orderModel";
import { ORDER_ACTION_MESSAGES } from "@/lib/orders/orderActionErrors";
import { detailDTO, lineDTO, ORDER_ID, stlLineDTO } from "@/lib/orders/orderFixtures";
import type { OrderDetailReadDTO } from "@/lib/orders/orderTypes";

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  message: "RAW BACKEND MESSAGE",
  detail: "RAW BACKEND DETAIL",
  raw: { status, code, detail: "RAW BACKEND DETAIL", ...extra },
});

const delivered = (overrides: Partial<OrderDetailReadDTO> = {}) =>
  detailDTO({ can_cancel: false, lines: [lineDTO({ fulfillment_status: "delivered" })], ...overrides });

function renderActions(dto: OrderDetailReadDTO) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const view = render(
    <QueryClientProvider client={queryClient}>
      <OrderCustomerActions order={adaptOrderDetail(dto)} />
    </QueryClientProvider>
  );
  return { ...view, queryClient, invalidate };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OrderCustomerActions — visibility", () => {
  it("renders nothing when the server state offers no action and records nothing", () => {
    const { container } = renderActions(detailDTO({ can_cancel: false }));
    expect(container).toBeEmptyDOMElement();
  });

  it("offers only Cancel on a cancellable order", () => {
    renderActions(detailDTO({ can_cancel: true }));
    const region = screen.getByRole("region", { name: "Order actions" });
    expect(within(region).getByRole("button", { name: "Cancel order" })).toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: "I received my items" })).not.toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: "Report a problem" })).not.toBeInTheDocument();
  });

  it("offers no cancel on an STL-only order (server can_cancel false), whatever the product types", () => {
    const { container } = renderActions(
      detailDTO({ can_cancel: false, fulfillment_method: null, lines: [stlLineDTO({ fulfillment_status: "delivered" })] })
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("offers receipt + report once a physical line is delivered", () => {
    renderActions(delivered());
    expect(screen.getByRole("button", { name: "I received my items" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Report a problem" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel order" })).not.toBeInTheDocument();
  });

  it("shows the server-recorded receipt and problem states", () => {
    renderActions(
      delivered({
        lines: [
          lineDTO({
            fulfillment_status: "delivered",
            receipt_confirmed_at: "2026-11-12T10:00:00Z",
            problem_reported_at: "2026-11-13T10:00:00Z",
          }),
        ],
      })
    );
    expect(screen.getByText(/You confirmed you received your items on 12 November 2026/)).toBeInTheDocument();
    expect(screen.getByText(/You reported a problem on 13 November 2026/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I received my items" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Report a problem" })).toBeInTheDocument();
  });
});

describe("OrderCustomerActions — cancel", () => {
  it("requires explicit confirmation, describes the effect, focuses the safe choice", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(ordersApi, "cancelOrder");
    renderActions(detailDTO({ can_cancel: true, lines: [lineDTO(), stlLineDTO()] }));
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel this order?" });
    expect(within(dialog).getByText(/STL files in this order aren't affected/)).toBeInTheDocument();
    expect(within(dialog).getByText(/won't need to pay for the cancelled items/)).toBeInTheDocument();
    // ADR-038 d23: a self-cancelled cash order counts as an open cash order for 24 hours.
    expect(within(dialog).getByText(/may not be able to choose cash payment for a new order for 24 hours/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Keep my order" })).toHaveFocus();
    expect(spy).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel order" })).toHaveFocus();
  });

  it("passes the optional reason through (max 500, never required)", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(ordersApi, "cancelOrder").mockResolvedValue(detailDTO({ status: "cancelled", can_cancel: false }));
    renderActions(detailDTO({ can_cancel: true }));
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    const dialog = screen.getByRole("dialog");
    const field = within(dialog).getByLabelText("Reason for cancelling (optional)");
    expect(field).toHaveAttribute("maxLength", "500");
    await user.type(field, "Ordered the wrong colour");
    await user.click(within(dialog).getByRole("button", { name: "Cancel order" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(ORDER_ID, "Ordered the wrong colour"));
  });

  it("mentions the refund for a paid online order", async () => {
    const user = userEvent.setup();
    renderActions(
      detailDTO({
        can_cancel: true,
        payment_method: "online",
        payment_due: false,
        payment: { status: "paid", provider: "mock", amount: { amount_cents: 2500, currency: "USD" } },
      })
    );
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    expect(screen.getByText(/cancelled items will be refunded/)).toBeInTheDocument();
    expect(screen.queryByText(/choose cash payment/)).not.toBeInTheDocument();
  });

  it("on success: closes, stores the server's detail, re-reads the order family, announces", async () => {
    const user = userEvent.setup();
    const cancelled = detailDTO({ status: "cancelled", can_cancel: false });
    const spy = vi.spyOn(ordersApi, "cancelOrder").mockResolvedValue(cancelled);
    const { queryClient, invalidate } = renderActions(detailDTO({ can_cancel: true }));
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel order" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(ORDER_ID, "");
    expect(queryClient.getQueryData(orderKeys.detail(ORDER_ID))).toBe(cancelled);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
    expect(screen.getByRole("status")).toHaveTextContent("Your cancellation went through");
  });

  it("on refusal: keeps the dialog open with safe copy, no backend text, re-reads the order", async () => {
    const user = userEvent.setup();
    vi.spyOn(ordersApi, "cancelOrder").mockRejectedValue(http(409, "ORDER_NOT_CANCELLABLE"));
    const { invalidate } = renderActions(detailDTO({ can_cancel: true }));
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel order" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.notCancellable);
    expect(dialog).not.toHaveTextContent("RAW");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
  });

  it("keeps the dialog and its error when the refusal's re-read leaves no action to offer", async () => {
    const user = userEvent.setup();
    vi.spyOn(ordersApi, "cancelOrder").mockRejectedValue(http(409, "ORDER_NOT_CANCELLABLE"));
    const queryClient = new QueryClient();
    const view = render(
      <QueryClientProvider client={queryClient}>
        <OrderCustomerActions order={adaptOrderDetail(detailDTO({ can_cancel: true }))} />
      </QueryClientProvider>
    );
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel order" }));
    await screen.findByRole("alert");
    // The canonical re-read now says can_cancel false.
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <OrderCustomerActions order={adaptOrderDetail(detailDTO({ can_cancel: false }))} />
      </QueryClientProvider>
    );
    expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.notCancellable);
    await user.click(screen.getByRole("button", { name: "Keep my order" }));
    expect(screen.queryByRole("region", { name: "Order actions" })).not.toBeInTheDocument();
  });

  it("blocks a double click while pending", async () => {
    const user = userEvent.setup();
    let resolve: (v: OrderDetailReadDTO) => void = () => {};
    const spy = vi.spyOn(ordersApi, "cancelOrder").mockImplementation(() => new Promise((r) => (resolve = r)));
    renderActions(detailDTO({ can_cancel: true }));
    await user.click(screen.getByRole("button", { name: "Cancel order" }));
    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel order" });
    await user.click(confirm);
    await user.click(confirm);
    expect(confirm).toBeDisabled();
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Keep my order" })).toBeDisabled();
    resolve(detailDTO({ status: "cancelled", can_cancel: false }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("OrderCustomerActions — confirm receipt", () => {
  it("posts once and announces the server-backed success", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn(ordersApi, "confirmReceipt")
      .mockResolvedValue(delivered({ lines: [lineDTO({ fulfillment_status: "delivered", receipt_confirmed_at: "2026-11-12T10:00:00Z" })] }));
    const { invalidate } = renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "I received my items" }));
    expect(spy).toHaveBeenCalledWith(ORDER_ID);
    expect(await screen.findByRole("status")).toHaveTextContent("We've recorded that you received your items");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: orderKeys.root });
  });

  it("maps 409 no_delivered_line to safe copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(ordersApi, "confirmReceipt").mockRejectedValue(
      http(409, "INVALID_STATE_TRANSITION", { reason: "no_delivered_line" })
    );
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "I received my items" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.noDeliveredLine);
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
  });

  it("maps an unverified account to the verify-email copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(ordersApi, "confirmReceipt").mockRejectedValue(http(403, "EMAIL_VERIFICATION_REQUIRED"));
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "I received my items" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.verifyEmail);
  });
});

describe("OrderCustomerActions — report a problem", () => {
  it("validates a blank message without calling the server", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(ordersApi, "reportProblem");
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    const dialog = screen.getByRole("dialog", { name: "Report a problem" });
    const field = within(dialog).getByLabelText("What's the problem?");
    expect(field).toHaveFocus();
    await user.type(field, "   ");
    await user.click(within(dialog).getByRole("button", { name: "Send report" }));
    expect(within(dialog).getByText("Describe the problem before sending.")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(spy).not.toHaveBeenCalled();
  });

  it("keeps the text after a recoverable failure, then succeeds on retry and resets", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn(ordersApi, "reportProblem")
      .mockRejectedValueOnce({ kind: "network", message: "x", raw: null })
      .mockResolvedValueOnce(delivered({ lines: [lineDTO({ fulfillment_status: "delivered", problem_reported_at: "2026-11-12T10:00:00Z" })] }));
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    const dialog = screen.getByRole("dialog");
    const field = within(dialog).getByLabelText("What's the problem?");
    await user.type(field, "The lid is cracked");
    await user.click(within(dialog).getByRole("button", { name: "Send report" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.uncertain);
    expect(field).toHaveValue("The lid is cracked");

    await user.click(within(dialog).getByRole("button", { name: "Send report" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(spy).toHaveBeenNthCalledWith(2, ORDER_ID, "The lid is cracked");
    expect(screen.getByRole("status")).toHaveTextContent("Your report was sent");

    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    expect(within(screen.getByRole("dialog")).getByLabelText("What's the problem?")).toHaveValue("");
  });

  it("keeps a draft across close and reopen", async () => {
    const user = userEvent.setup();
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    await user.type(screen.getByLabelText("What's the problem?"), "Draft");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    expect(screen.getByLabelText("What's the problem?")).toHaveValue("Draft");
  });

  it("maps a server 422 to safe copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(ordersApi, "reportProblem").mockRejectedValue(http(422, "VALIDATION_ERROR"));
    renderActions(delivered());
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    await user.type(screen.getByLabelText("What's the problem?"), "ok");
    await user.click(screen.getByRole("button", { name: "Send report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(ORDER_ACTION_MESSAGES.invalidMessage);
  });
});
