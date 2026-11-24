import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { promotionsAdminApi } from "@/lib/admin/promotions/promotionsAdminApi";
import { productsAdminApi } from "@/lib/admin/products/productsAdminApi";
import type { AdminPromotionRead } from "@/lib/promotions/promotionTypes";
import AdminPromotionsPage from "./page";
import AdminNewPromotionPage from "./new/page";
import AdminPromotionPage from "./[id]/page";

const mockPush = vi.fn();
const PROMO_ID = "11111111-1111-4111-8111-111111111111";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: PROMO_ID }),
}));

function promotion(over: Partial<AdminPromotionRead> = {}): AdminPromotionRead {
  return {
    id: PROMO_ID,
    name: "Eid Sale",
    badge_text: null,
    discount_type: "percentage",
    discount_value: 20,
    scope: "all",
    product_ids: [],
    starts_at: "2026-12-01T08:00:00Z",
    ends_at: "2026-12-10T08:00:00Z",
    active: true,
    status: "active",
    created_at: "2026-11-20T00:00:00Z",
    updated_at: "2026-11-20T00:00:00Z",
    ...over,
  };
}

function renderWithQuery(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  mockPush.mockReset();
  vi.spyOn(productsAdminApi, "listProducts").mockResolvedValue({ items: [], next_cursor: null } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("/admin/promotions", () => {
  it("lists promotions with discount, scope, dates and the server's status", async () => {
    vi.spyOn(promotionsAdminApi, "listPromotions").mockResolvedValue({
      items: [
        promotion(),
        promotion({ id: "p-2", name: "Christmas", discount_type: "fixed", discount_value: 500, status: "scheduled" }),
        promotion({ id: "p-3", name: "Old", status: "ended" }),
        promotion({ id: "p-4", name: "Paused", active: false, status: "inactive", scope: "selected", product_ids: ["a"] }),
      ],
    });
    renderWithQuery(<AdminPromotionsPage />);

    expect(await screen.findByRole("link", { name: "Eid Sale" })).toHaveAttribute("href", `/admin/promotions/${PROMO_ID}`);
    expect(screen.getByRole("heading", { level: 1, name: "Promotions" })).toBeInTheDocument();
    expect(screen.getAllByText("20% off")).toHaveLength(3);
    expect(screen.getByText("$5 off")).toBeInTheDocument();
    expect(screen.getByText("Selected products (1)")).toBeInTheDocument();
    for (const label of ["Active", "Scheduled", "Ended", "Inactive"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /create promotion/i })).toHaveAttribute("href", "/admin/promotions/new");
  });

  it("shows an empty state, not a fake campaign, when there are none", async () => {
    vi.spyOn(promotionsAdminApi, "listPromotions").mockResolvedValue({ items: [] });
    renderWithQuery(<AdminPromotionsPage />);
    expect(await screen.findByText(/No promotions yet/)).toBeInTheDocument();
  });
});

describe("/admin/promotions/new", () => {
  it("blocks obvious mistakes locally without calling the server", async () => {
    const create = vi.spyOn(promotionsAdminApi, "createPromotion");
    const user = userEvent.setup();
    renderWithQuery(<AdminNewPromotionPage />);

    await user.type(screen.getByLabelText("Discount value (%)"), "150");
    await user.click(screen.getByRole("button", { name: "Save promotion" }));

    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a promotion name.")).toBeInTheDocument();
    expect(screen.getByText("Enter a whole percentage from 1 to 100.")).toBeInTheDocument();
  });

  it("creates with exactly the backend's fields, once, then returns to the list", async () => {
    let resolve: (value: AdminPromotionRead) => void = () => undefined;
    const create = vi
      .spyOn(promotionsAdminApi, "createPromotion")
      .mockImplementation(() => new Promise((r) => (resolve = r)));
    const user = userEvent.setup();
    renderWithQuery(<AdminNewPromotionPage />);

    await user.type(screen.getByLabelText("Promotion name"), "Independence Day");
    await user.type(screen.getByLabelText("Badge text (optional)"), "22 Nov");
    await user.selectOptions(screen.getByLabelText("Discount type"), "fixed");
    await user.type(screen.getByLabelText("Discount value (USD)"), "5");
    await user.selectOptions(screen.getByLabelText("Applies to"), "physical");
    const save = screen.getByRole("button", { name: "Save promotion" });
    await user.click(save);
    await user.click(save);

    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0]![0]).toMatchObject({
      name: "Independence Day",
      badge_text: "22 Nov",
      discount_type: "fixed",
      discount_value: 500,
      scope: "physical",
      product_ids: [],
      active: true,
    });
    resolve(promotion());
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/promotions"));
  });

  it("puts a server validation refusal on its field, never raw server text", async () => {
    vi.spyOn(promotionsAdminApi, "createPromotion").mockRejectedValue({
      kind: "http",
      status: 422,
      code: "VALIDATION_ERROR",
      message: "RAW",
      errors: [{ loc: ["body", "product_ids"], msg: "RAW detail", type: "value_error" }],
    });
    const user = userEvent.setup();
    renderWithQuery(<AdminNewPromotionPage />);
    await user.type(screen.getByLabelText("Promotion name"), "Eid");
    await user.type(screen.getByLabelText("Discount value (%)"), "10");
    await user.click(screen.getByRole("button", { name: "Save promotion" }));
    expect(await screen.findByText("Choose existing products only.")).toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).toBeNull();
  });
});

describe("/admin/promotions/[id]", () => {
  it("loads the promotion, switches it off with one Save, and confirms", async () => {
    vi.spyOn(promotionsAdminApi, "getPromotion").mockResolvedValue(promotion());
    const update = vi
      .spyOn(promotionsAdminApi, "updatePromotion")
      .mockResolvedValue(promotion({ active: false, status: "inactive" }));
    const user = userEvent.setup();
    renderWithQuery(<AdminPromotionPage />);

    const heading = await screen.findByRole("heading", { level: 1, name: "Eid Sale" });
    expect(within(heading.parentElement!).getByText("Active")).toBeInTheDocument();
    expect(screen.getByLabelText("Promotion name")).toHaveValue("Eid Sale");
    const active = screen.getByRole("switch", { name: "Active" });
    expect(active).toHaveAttribute("aria-checked", "true");
    await user.click(active);
    await user.click(screen.getByRole("button", { name: "Save promotion" }));

    expect(update).toHaveBeenCalledTimes(1);
    expect(update.mock.calls[0]![0]).toBe(PROMO_ID);
    expect(update.mock.calls[0]![1]).toMatchObject({ active: false, discount_value: 20, name: "Eid Sale" });
    expect(await screen.findByText("Promotion saved.")).toBeInTheDocument();
    expect(within(heading.parentElement!).getByText("Inactive")).toBeInTheDocument();
  });

  it("shows not-found for an unknown promotion", async () => {
    vi.spyOn(promotionsAdminApi, "getPromotion").mockRejectedValue({ kind: "http", status: 404, code: "NOT_FOUND", message: "x" });
    renderWithQuery(<AdminPromotionPage />);
    expect(await screen.findByRole("heading", { level: 1 })).not.toHaveTextContent("Eid Sale");
  });
});
