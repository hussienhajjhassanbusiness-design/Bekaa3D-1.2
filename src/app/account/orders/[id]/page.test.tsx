import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AccountOrderDetailPage from "./page";
import { usePolledOrder } from "@/lib/orders/usePolledOrder";
import { useRetryPayment } from "@/lib/orders/useRetryPayment";
import { usePublicSettings } from "@/lib/settings/usePublicSettings";
import { detailDTO, ORDER_ID, pendingOnlineDetailDTO } from "@/lib/orders/orderFixtures";

let mockId = ORDER_ID;
vi.mock("next/navigation", () => ({ useParams: () => ({ id: mockId }) }));
vi.mock("@/lib/orders/usePolledOrder", () => ({ usePolledOrder: vi.fn() }));
vi.mock("@/lib/orders/useRetryPayment", () => ({ useRetryPayment: vi.fn() }));
vi.mock("@/lib/settings/usePublicSettings", () => ({ usePublicSettings: vi.fn() }));
vi.mock("@/lib/orders/useOrderActions", () => ({
  useOrderAction: () => ({ state: { kind: "idle" }, submit: vi.fn(), reset: vi.fn() }),
}));

const mockedUsePolledOrder = vi.mocked(usePolledOrder);
const retryStart = vi.fn();
const retryResume = vi.fn();
const checkAgain = vi.fn();
let polledState = { polling: false, timedOut: false };

function result(overrides: Record<string, unknown> = {}) {
  return { data: undefined, isError: false, error: null, refetch: vi.fn(), ...overrides };
}

// The page's one order reader is usePolledOrder (canonical detail query).
const mockedUseMyOrder = {
  mockReturnValue(query: ReturnType<typeof result>) {
    mockedUsePolledOrder.mockReturnValue({ query, transient: false, ...polledState, checkAgain } as never);
  },
};

beforeEach(() => {
  mockId = ORDER_ID;
  mockedUsePolledOrder.mockReset();
  polledState = { polling: false, timedOut: false };
  retryStart.mockReset();
  retryResume.mockReset();
  checkAgain.mockReset();
  vi.mocked(useRetryPayment).mockReturnValue({ state: { kind: "idle" }, start: retryStart, resume: retryResume });
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
    expect(mockedUsePolledOrder).toHaveBeenCalledWith(ORDER_ID, { enabled: true });
  });

  it("mounts the Order actions section from the same canonical order (FVS-031)", () => {
    mockedUseMyOrder.mockReturnValue(result({ data: detailDTO({ can_cancel: true }) }));
    render(<AccountOrderDetailPage />);
    const region = screen.getByRole("region", { name: "Order actions" });
    expect(region).toContainElement(screen.getByRole("button", { name: "Cancel order" }));
    // Separate from the payment section.
    expect(screen.getByRole("region", { name: "Payment" })).not.toContainElement(region);
  });

  it("offers no customer action when the server state allows none", () => {
    mockedUseMyOrder.mockReturnValue(result({ data: detailDTO({ can_cancel: false }) }));
    render(<AccountOrderDetailPage />);
    expect(screen.queryByRole("region", { name: "Order actions" })).not.toBeInTheDocument();
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
    expect(mockedUsePolledOrder).toHaveBeenCalledWith("not-a-uuid", { enabled: false });
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

  describe("payment (FVS-027)", () => {
    it("offers Retry payment only when the server's can_retry_payment is true, and starts the one retry flow", async () => {
      mockedUseMyOrder.mockReturnValue(
        result({ data: pendingOnlineDetailDTO({ can_retry_payment: true, payment: { status: "failed", provider: "mock", amount: { amount_cents: 2500, currency: "USD" } } }) })
      );
      render(<AccountOrderDetailPage />);
      await userEvent.setup().click(screen.getByRole("button", { name: "Retry payment" }));
      expect(retryStart).toHaveBeenCalledTimes(1);
      expect(vi.mocked(useRetryPayment)).toHaveBeenCalledWith(ORDER_ID);
    });

    it("no Retry payment while can_retry_payment is false", () => {
      mockedUseMyOrder.mockReturnValue(result({ data: pendingOnlineDetailDTO({ can_retry_payment: false }) }));
      render(<AccountOrderDetailPage />);
      expect(screen.queryByRole("button", { name: /retry payment/i })).not.toBeInTheDocument();
    });

    it("shows the bounded verification state and Check again re-reads", async () => {
      polledState = { polling: false, timedOut: true };
      mockedUseMyOrder.mockReturnValue(result({ data: pendingOnlineDetailDTO() }));
      render(<AccountOrderDetailPage />);
      expect(screen.getByRole("status")).toHaveTextContent(/haven't received a confirmation/i);
      await userEvent.setup().click(screen.getByRole("button", { name: "Check again" }));
      expect(checkAgain).toHaveBeenCalledTimes(1);
    });

    it("says it is checking while polling", () => {
      polledState = { polling: true, timedOut: false };
      mockedUseMyOrder.mockReturnValue(result({ data: pendingOnlineDetailDTO() }));
      render(<AccountOrderDetailPage />);
      expect(screen.getByRole("status")).toHaveTextContent(/checking for a payment update/i);
    });

    it("a cash order never shows retry or verification, even with stray flags", () => {
      polledState = { polling: true, timedOut: true };
      mockedUseMyOrder.mockReturnValue(result({ data: detailDTO({ can_retry_payment: true, hold_expires_at: "2026-11-10T10:00:00Z" }) }));
      render(<AccountOrderDetailPage />);
      expect(screen.queryByRole("button", { name: /retry|check again|continue/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/checking for a payment update|time left/i)).not.toBeInTheDocument();
    });
  });
});
