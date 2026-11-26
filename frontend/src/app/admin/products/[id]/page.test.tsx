import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminProductDetailPage from "./page";
import { useAdminProduct } from "@/lib/admin/products/useAdminProduct";
import { useAdminProductDelete } from "@/lib/admin/products/useAdminProductMutations";
import type { RawAdminProductDetail } from "@/lib/admin/products/productAdminTypes";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "p1" }), useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/admin/products/useAdminProduct", () => ({ useAdminProduct: vi.fn() }));
vi.mock("@/lib/admin/products/useAdminProductMutations", () => ({
  useAdminProductDelete: vi.fn(),
  useAdminProductCreate: vi.fn(),
  useAdminProductUpdate: vi.fn(),
}));

const mockedUseAdminProduct = vi.mocked(useAdminProduct);
const mockedUseAdminProductDelete = vi.mocked(useAdminProductDelete);

const PRODUCT: RawAdminProductDetail = {
  id: "p1",
  type: "physical",
  category_id: "cat1",
  name: "Moon Lamp",
  slug: "moon-lamp",
  price: { amount_cents: 1800, currency: "USD" },
  description: null,
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  is_visible: true,
  is_featured: false,
  is_available: true,
  material_id: null,
  colour_id: null,
  dimensions: null,
  weight_grams: null,
  production_lead_time_days: 2,
  batch_size: 2,
  max_quantity_per_line: 5,
  purchase_mode: "both",
  version: 3,
  average_rating: 0,
  review_count: 0,
  wishlist_count: 0,
  deleted_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  images: [],
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminProduct>> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, ...overrides } as ReturnType<
    typeof useAdminProduct
  >;
}

beforeEach(() => {
  mockPush.mockReset();
  mockedUseAdminProduct.mockReset();
  mockedUseAdminProductDelete.mockReset();
  mockedUseAdminProductDelete.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
});

describe("AdminProductDetailPage", () => {
  it("shows real not-found UX for a 404", () => {
    mockedUseAdminProduct.mockReturnValue(
      queryResult({ isError: true, error: { kind: "http", status: 404, code: "NOT_FOUND", message: "x", raw: undefined } })
    );
    render(<AdminProductDetailPage />);
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
  });

  it("renders product details with an Edit link", () => {
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    render(<AdminProductDetailPage />);
    expect(screen.getByRole("heading", { name: "Moon Lamp" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/admin/products/p1/edit");
  });

  it("deleting requires confirmation, sends the current version, then navigates to the list", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminProductDelete.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductDetailPage />);

    await user.click(screen.getByRole("button", { name: /delete/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Delete" }).at(-1)!);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ productId: "p1", version: 3 }));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/admin/products"));
  });

  it("cancelling the delete confirmation never calls the mutation", async () => {
    const mutateAsync = vi.fn();
    mockedUseAdminProductDelete.mockReturnValue({ mutateAsync, isPending: false } as never);
    mockedUseAdminProduct.mockReturnValue(queryResult({ data: PRODUCT }));
    const user = userEvent.setup();
    render(<AdminProductDetailPage />);

    await user.click(screen.getByRole("button", { name: /delete/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
