import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import AccountOrdersPage from "./page";
import { useMyOrders } from "@/lib/orders/useMyOrders";
import { pageDTO, summaryDTO } from "@/lib/orders/orderFixtures";

vi.mock("@/lib/orders/useMyOrders", () => ({ useMyOrders: vi.fn() }));
const mocked = vi.mocked(useMyOrders);

function result(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    isFetchNextPageError: false,
    fetchNextPage: vi.fn(),
    ...overrides,
  } as never;
}

beforeEach(() => mocked.mockReset());

describe("/account/orders", () => {
  it("renders every loaded page's orders in order", () => {
    mocked.mockReturnValue(
      result({
        data: {
          pages: [pageDTO([summaryDTO({ id: "a", order_number: "N-1" })], "c2"), pageDTO([summaryDTO({ id: "b", order_number: "N-2" })])],
        },
      })
    );
    render(<AccountOrdersPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Orders" })).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /^Order N-/ });
    expect(links.map((link) => link.textContent)).toEqual(["Order N-1", "Order N-2"]);
  });

  it("keeps loaded orders and shows a load-more failure instead of replacing the list", () => {
    mocked.mockReturnValue(
      result({
        data: { pages: [pageDTO([summaryDTO()], "c2")] },
        error: { kind: "network", message: "x", raw: {} },
        hasNextPage: true,
        isFetchNextPageError: true,
      })
    );
    render(<AccountOrdersPage />);
    expect(screen.getByRole("listitem")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load more orders/i);
  });

  it("shows the first-page failure", () => {
    mocked.mockReturnValue(result({ error: { kind: "network", message: "x", raw: {} } }));
    render(<AccountOrdersPage />);
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your orders/i);
  });
});
