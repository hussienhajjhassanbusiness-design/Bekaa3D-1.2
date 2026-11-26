import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminCashBlocksPage from "./page";
import { apiClient } from "@/lib/api/apiClient";
import { cashBlocksApi, type CashPaymentBlockReadDTO } from "@/lib/admin/cashBlocks/cashBlocksApi";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({ useSearchParams: () => search }));

const block = (overrides: Partial<CashPaymentBlockReadDTO> = {}): CashPaymentBlockReadDTO => ({
  id: "b-1",
  customer_id: "c-1",
  order_id: "o-1",
  order_number: "B3D-CASH0001",
  reason: "refused",
  created_at: "2026-11-10T10:00:00Z",
  active: true,
  cleared_at: null,
  cleared_by: null,
  ...overrides,
});

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AdminCashBlocksPage />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  search = new URLSearchParams();
});

describe("cashBlocksApi", () => {
  it("lists by query, searches by phone in a CSRF POST body (never the URL), clears with CSRF", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    await cashBlocksApi.listBlocks({ customer_id: "c-1", active: true });
    await cashBlocksApi.searchBlocks({ phone: "70 123 456", active: true });
    await cashBlocksApi.clearBlock("b-1");
    expect(get).toHaveBeenCalledWith("/api/v1/admin/cash-blocks?customer_id=c-1&active=true");
    expect(post.mock.calls).toEqual([
      ["/api/v1/admin/cash-blocks/search", { phone: "70 123 456", active: true }, { csrf: true }],
      ["/api/v1/admin/cash-blocks/b-1/clear", undefined, { csrf: true }],
    ]);
  });
});

describe("/admin/cash-blocks", () => {
  it("lists active blocks with reason, clears one after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(cashBlocksApi, "listBlocks").mockResolvedValue({ items: [block()], next_cursor: null });
    const clear = vi.spyOn(cashBlocksApi, "clearBlock").mockResolvedValue(block({ active: false, cleared_at: "2026-11-12T00:00:00Z" }));
    renderPage();
    expect(await screen.findByText("Customer refused the order")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear block" }));
    const dialog = screen.getByRole("dialog", { name: "Clear this cash block?" });
    await user.click(within(dialog).getByRole("button", { name: "Clear block" }));
    await waitFor(() => expect(clear).toHaveBeenCalledWith("b-1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("phone search uses the POST; an invalid phone gets safe copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(cashBlocksApi, "listBlocks").mockResolvedValue({ items: [], next_cursor: null });
    const searchSpy = vi
      .spyOn(cashBlocksApi, "searchBlocks")
      .mockRejectedValueOnce({ kind: "http", status: 422, code: "VALIDATION_ERROR", message: "RAW", raw: {} })
      .mockResolvedValueOnce({ items: [block({ order_number: "B3D-FOUND" })], next_cursor: null });
    renderPage();
    await user.type(screen.getByLabelText("Find by contact phone"), "123");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid Lebanese phone number.");
    await user.clear(screen.getByLabelText("Find by contact phone"));
    await user.type(screen.getByLabelText("Find by contact phone"), "70123456");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("B3D-FOUND")).toBeInTheDocument();
    expect(searchSpy).toHaveBeenLastCalledWith({ phone: "70123456", active: true });
  });

  it("cleared blocks offer no action; ?customer_id narrows the list", async () => {
    search = new URLSearchParams({ customer_id: "7c1a7e2b-5f2d-4c1e-9a4b-1d2e3f4a5b6c" });
    const list = vi.spyOn(cashBlocksApi, "listBlocks").mockResolvedValue({ items: [block({ active: false, cleared_at: "2026-11-12T00:00:00Z" })], next_cursor: null });
    renderPage();
    expect(await screen.findByText("Cleared", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear block" })).not.toBeInTheDocument();
    expect(list.mock.calls[0]![0]).toEqual(expect.objectContaining({ customer_id: "7c1a7e2b-5f2d-4c1e-9a4b-1d2e3f4a5b6c", active: true }));
  });
});
