import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminOrderDetailPage from "./page";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import { adminDetailDTO, ADMIN_ORDER_ID } from "@/lib/admin/orders/adminOrderFixtures";

let mockId = ADMIN_ORDER_ID;
vi.mock("next/navigation", () => ({ useParams: () => ({ id: mockId }) }));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AdminOrderDetailPage />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  mockId = ADMIN_ORDER_ID;
});

describe("/admin/orders/[id]", () => {
  it("renders the order", async () => {
    vi.spyOn(adminOrdersApi, "getOrder").mockResolvedValue(adminDetailDTO());
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Order B3D-ADMIN001" })).toBeInTheDocument();
  });

  it("404 and a malformed id both read as not found; a malformed id is never sent", async () => {
    vi.spyOn(adminOrdersApi, "getOrder").mockRejectedValue({ kind: "http", status: 404, code: "NOT_FOUND", message: "RAW", raw: {} });
    renderPage();
    expect(await screen.findByRole("heading", { name: /Page not found/ })).toBeInTheDocument();

    const spy = vi.spyOn(adminOrdersApi, "getOrder");
    spy.mockClear();
    mockId = "not-a-uuid";
    renderPage();
    expect(spy).not.toHaveBeenCalled();
  });
});
