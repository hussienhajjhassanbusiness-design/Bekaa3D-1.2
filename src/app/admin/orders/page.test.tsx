import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminOrdersPage from "./page";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import { adminSummaryDTO } from "@/lib/admin/orders/adminOrderFixtures";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AdminOrdersPage />
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("/admin/orders", () => {
  it("lists the queue with server-backed fields and a link to each order", async () => {
    vi.spyOn(adminOrdersApi, "listOrders").mockResolvedValue({ items: [adminSummaryDTO()], next_cursor: null });
    renderPage();
    const link = await screen.findByRole("link", { name: "B3D-ADMIN001" });
    expect(link).toHaveAttribute("href", "/admin/orders/3c1a7e2b-5f2d-4c1e-9a4b-1d2e3f4a5b6c");
    expect(screen.getByText("rana@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Cash due/, { selector: "span" })).toHaveTextContent("$36.00");
  });

  it("sends exactly the backend's filters; the status list never offers pending_payment", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(adminOrdersApi, "listOrders").mockResolvedValue({ items: [], next_cursor: null });
    renderPage();
    await screen.findByText("No orders match these filters.");
    const statusOptions = Array.from((screen.getByLabelText("Status") as HTMLSelectElement).options).map((o) => o.value);
    expect(statusOptions).not.toContain("pending_payment");
    await user.selectOptions(screen.getByLabelText("Status"), "in_progress");
    await user.selectOptions(screen.getByLabelText("Fulfillment"), "pickup");
    await user.selectOptions(screen.getByLabelText("Payment"), "cash");
    await user.selectOptions(screen.getByLabelText("Cash due"), "true");
    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith({
        status: "in_progress",
        fulfillment_method: "pickup",
        payment_method: "cash",
        payment_due: true,
        order_number: undefined,
        cursor: undefined,
      })
    );
  });

  it("shows safe copy on failure", async () => {
    vi.spyOn(adminOrdersApi, "listOrders").mockRejectedValue({ kind: "network", message: "RAW", raw: null });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't reach the server. Please try again.");
  });
});
