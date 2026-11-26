import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import AdminProductsPage from "./page";
import { useAdminProducts } from "@/lib/admin/products/useAdminProducts";
import type { RawAdminProductDetail } from "@/lib/admin/products/productAdminTypes";

vi.mock("@/lib/admin/products/useAdminProducts", () => ({ useAdminProducts: vi.fn() }));
const mockedUseAdminProducts = vi.mocked(useAdminProducts);

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
  version: 1,
  average_rating: 0,
  review_count: 0,
  wishlist_count: 0,
  deleted_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  images: [],
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminProducts>> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, ...overrides } as ReturnType<
    typeof useAdminProducts
  >;
}

beforeEach(() => {
  mockedUseAdminProducts.mockReset();
});

describe("AdminProductsPage", () => {
  it("shows a loading state", () => {
    mockedUseAdminProducts.mockReturnValue(queryResult({ isLoading: true }));
    render(<AdminProductsPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    mockedUseAdminProducts.mockReturnValue(queryResult({ data: { items: [], next_cursor: null } }));
    render(<AdminProductsPage />);
    expect(screen.getByText("No products found.")).toBeInTheDocument();
  });

  it("renders a row with price, visibility, and availability", () => {
    mockedUseAdminProducts.mockReturnValue(queryResult({ data: { items: [PRODUCT], next_cursor: null } }));
    render(<AdminProductsPage />);
    expect(screen.getByText("Moon Lamp")).toBeInTheDocument();
    expect(screen.getByText("$18.00")).toBeInTheDocument();
    expect(screen.getByText("Visible")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute("href", "/admin/products/p1");
  });

  it("has a link to create a new product", () => {
    mockedUseAdminProducts.mockReturnValue(queryResult({ data: { items: [], next_cursor: null } }));
    render(<AdminProductsPage />);
    expect(screen.getByRole("link", { name: /new product/i })).toHaveAttribute("href", "/admin/products/new");
  });
});
