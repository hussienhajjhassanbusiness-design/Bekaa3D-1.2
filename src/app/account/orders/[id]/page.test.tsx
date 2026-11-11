import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AccountOrderDetailPage from "./page";
import { useMyOrder } from "@/lib/orders/useMyOrders";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { detailDTO, ORDER_ID } from "@/lib/orders/orderFixtures";

let mockId = ORDER_ID;
vi.mock("next/navigation", () => ({ useParams: () => ({ id: mockId }) }));
vi.mock("@/lib/orders/useMyOrders", () => ({ useMyOrder: vi.fn() }));
vi.mock("@/lib/settings/usePublicSettings", () => ({ usePublicSettings: vi.fn() }));

const mockedUseMyOrder = vi.mocked(useMyOrder);

function result(overrides: Record<string, unknown> = {}) {
  return { data: undefined, isError: false, error: null, refetch: vi.fn(), ...overrides } as never;
}

beforeEach(() => {
  mockId = ORDER_ID;
  mockedUseMyOrder.mockReset();
  vi.mocked(usePublicSettings).mockReturnValue({ data: undefined } as never);
});

describe("/account/orders/[id]", () => {
  it("shows a loading state", () => {
    mockedUseMyOrder.mockReturnValue(result());
    render(<AccountOrderDetailPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders the order", () => {
    mockedUseMyOrder.mockReturnValue(result({ data: detailDTO() }));
    render(<AccountOrderDetailPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Order B3D-2026-000123" })).toBeInTheDocument();
    expect(mockedUseMyOrder).toHaveBeenCalledWith(ORDER_ID, { enabled: true });
  });

  it("shows the same not-found state for a 404 (unknown or another customer's order)", () => {
    mockedUseMyOrder.mockReturnValue(
      result({ isError: true, error: { kind: "http", status: 404, code: "NOT_FOUND", detail: "Not Found", message: "Not Found", raw: {} } })
    );
    render(<AccountOrderDetailPage />);
    expect(screen.getByRole("heading", { name: "Order not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view your orders/i })).toHaveAttribute("href", "/account/orders");
    expect(screen.queryByText(/forbidden|another customer|not yours/i)).not.toBeInTheDocument();
  });

  it("never calls the API for a malformed id and shows not-found", () => {
    mockId = "not-a-uuid";
    mockedUseMyOrder.mockReturnValue(result());
    render(<AccountOrderDetailPage />);
    expect(mockedUseMyOrder).toHaveBeenCalledWith("not-a-uuid", { enabled: false });
    expect(screen.getByRole("heading", { name: "Order not found" })).toBeInTheDocument();
  });

  it("shows session-expired copy for AUTH_REQUIRED after a failed refresh", () => {
    mockedUseMyOrder.mockReturnValue(
      result({ isError: true, error: { kind: "http", status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} } })
    );
    render(<AccountOrderDetailPage />);
    expect(screen.getByRole("alert")).toHaveTextContent(/session has expired/i);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      `/login?returnTo=${encodeURIComponent(`/account/orders/${ORDER_ID}`)}`
    );
  });

  it("shows safe copy and retry for other failures, never the server text", async () => {
    const refetch = vi.fn();
    mockedUseMyOrder.mockReturnValue(
      result({
        isError: true,
        refetch,
        error: { kind: "http", status: 503, code: "SERVICE_UNAVAILABLE", detail: "redis down at 10.0.0.3", message: "redis", raw: {} },
      })
    );
    render(<AccountOrderDetailPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load this order. Please try again.");
    expect(screen.queryByText(/redis/i)).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
