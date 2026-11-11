import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderHistoryList, type OrderHistoryListProps } from "./OrderHistoryList";
import { adaptOrderSummary } from "@/lib/orders/orderModel";
import { ORDER_ID, summaryDTO } from "@/lib/orders/orderFixtures";

function renderList(overrides: Partial<OrderHistoryListProps> = {}) {
  const props: OrderHistoryListProps = {
    orders: [],
    isLoading: false,
    error: null,
    onRetry: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    onLoadMore: vi.fn(),
    loadMoreFailed: false,
    ...overrides,
  };
  render(<OrderHistoryList {...props} />);
  return props;
}

describe("OrderHistoryList", () => {
  it("shows a loading state", () => {
    renderList({ isLoading: true });
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state that points to the shop", () => {
    renderList();
    expect(screen.getByText(/haven't placed any orders yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /browse the shop/i })).toHaveAttribute("href", "/shop");
  });

  it("shows safe copy and a retry for a failure, never the server's detail", async () => {
    const user = userEvent.setup();
    const props = renderList({
      error: { kind: "http", status: 500, code: "INTERNAL_ERROR", detail: "Traceback secret", message: "Traceback secret", raw: {} },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load your orders. Please try again.");
    expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it("shows session-expired copy with a sign-in link for an auth failure", () => {
    renderList({ error: { kind: "http", status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} } });
    expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/login?returnTo=%2Faccount%2Forders"
    );
  });

  it("renders a cash delivery order with its payment due, linking to the detail page", () => {
    renderList({ orders: [adaptOrderSummary(summaryDTO())] });
    const item = screen.getByRole("listitem");
    const link = within(item).getByRole("link", { name: /order B3D-2026-000123/i });
    expect(link).toHaveAttribute("href", `/account/orders/${ORDER_ID}`);
    expect(item).toHaveTextContent("In progress");
    expect(item).toHaveTextContent("10 November 2026");
    expect(item).toHaveTextContent("Delivery");
    expect(item).toHaveTextContent("Cash");
    expect(item).toHaveTextContent(/payment due.*\$25\.00/i);
    expect(item).not.toHaveTextContent(/paid/i);
  });

  it("renders a pending online order as awaiting payment, never paid", () => {
    renderList({
      orders: [
        adaptOrderSummary(
          summaryDTO({ status: "pending_payment", payment_method: "online", payment_due: false, amount_due: null })
        ),
      ],
    });
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("Awaiting payment");
    expect(item).toHaveTextContent("Online payment");
    expect(item).not.toHaveTextContent(/payment due/i);
    expect(item).not.toHaveTextContent(/\bpaid\b/i);
  });

  it("labels an STL-only order and pickup orders", () => {
    renderList({
      orders: [
        adaptOrderSummary(summaryDTO({ id: "a", order_number: "N1", fulfillment_method: null })),
        adaptOrderSummary(summaryDTO({ id: "b", order_number: "N2", fulfillment_method: "pickup" })),
      ],
    });
    const [stl, pickup] = screen.getAllByRole("listitem");
    expect(stl).toHaveTextContent("STL files only");
    expect(pickup).toHaveTextContent("Pickup");
  });

  it("degrades an unknown status without crashing", () => {
    renderList({ orders: [adaptOrderSummary(summaryDTO({ status: "brand_new" as never }))] });
    expect(screen.getByRole("listitem")).toHaveTextContent("Status unavailable");
  });

  it("offers Load more only when the server has another page", async () => {
    const user = userEvent.setup();
    const props = renderList({ orders: [adaptOrderSummary(summaryDTO())], hasNextPage: true });
    await user.click(screen.getByRole("button", { name: /load more orders/i }));
    expect(props.onLoadMore).toHaveBeenCalled();
  });

  it("hides Load more on the last page", () => {
    renderList({ orders: [adaptOrderSummary(summaryDTO())], hasNextPage: false });
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("keeps loaded orders visible when loading more fails", () => {
    renderList({ orders: [adaptOrderSummary(summaryDTO())], hasNextPage: true, loadMoreFailed: true });
    expect(screen.getByRole("listitem")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load more orders/i);
  });
});
