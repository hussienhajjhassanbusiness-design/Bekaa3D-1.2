import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminStlDeliveriesPage from "./page";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import { adminDetailDTO, stlDeliveryDTO } from "@/lib/admin/orders/adminOrderFixtures";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AdminStlDeliveriesPage />
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("/admin/stl-deliveries", () => {
  it("lists owed STL lines; Mark emailed confirms and posts the line's awaiting_delivery -> delivered", async () => {
    const user = userEvent.setup();
    const row = stlDeliveryDTO();
    vi.spyOn(adminOrdersApi, "listStlDeliveries").mockResolvedValue({ items: [row], next_cursor: null });
    const spy = vi.spyOn(adminOrdersApi, "transitionLine").mockResolvedValue(adminDetailDTO());
    renderPage();
    await screen.findByText("Dragon STL");
    expect(screen.queryByText(/download|upload/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mark emailed" }));
    const dialog = screen.getByRole("dialog", { name: "Mark this STL file emailed?" });
    expect(dialog).toHaveTextContent("sami@example.com");
    await user.click(within(dialog).getByRole("button", { name: "Mark emailed" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith(row.order_id, row.item_id, { target_status: "delivered" });
  });

  it("an already-delivered line is refused with safe copy, dialog kept", async () => {
    const user = userEvent.setup();
    vi.spyOn(adminOrdersApi, "listStlDeliveries").mockResolvedValue({ items: [stlDeliveryDTO()], next_cursor: null });
    vi.spyOn(adminOrdersApi, "transitionLine").mockRejectedValue({
      kind: "http",
      status: 409,
      code: "INVALID_STATE_TRANSITION",
      message: "RAW",
      raw: { reason: "already_delivered", fulfilled_at: "2026-11-11T00:00:00Z" },
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Mark emailed" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark emailed" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("This STL file is already marked as emailed.");
  });

  it("empty queue", async () => {
    vi.spyOn(adminOrdersApi, "listStlDeliveries").mockResolvedValue({ items: [], next_cursor: null });
    renderPage();
    expect(await screen.findByText("No STL files are waiting to be emailed.")).toBeInTheDocument();
  });
});
