import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductGrid } from "./ProductGrid";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

// Phase 6D: the wishlist heart needs the auth context; it has its own tests
// (src/components/wishlist), so it is stubbed out of these card tests.
vi.mock("@/components/wishlist/WishlistButton", () => ({ WishlistButton: () => null }));

const product: ProductCardModel = {
  id: "p1",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  coverImage: null,
  price: { amountCents: 1800, currency: "USD" },
  category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
  material: null,
  colour: null,
  isAvailable: true,
  purchaseMode: "both",
  averageRating: 0,
  reviewCount: 0,
  isFeatured: false,
};

describe("ProductGrid", () => {
  it("shows a loading spinner while loading", () => {
    render(<ProductGrid products={[]} isLoading isError={false} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an error alert on error, not the empty state", () => {
    render(<ProductGrid products={[]} isLoading={false} isError />);
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn.t load products/i);
  });

  it("shows the empty state with a clear-filters action when there are no products", async () => {
    const onClearFilters = vi.fn();
    render(<ProductGrid products={[]} isLoading={false} isError={false} onClearFilters={onClearFilters} />);

    expect(screen.getByText(/no products match your filters/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    expect(onClearFilters).toHaveBeenCalled();
  });

  it("renders a semantic list of product cards", () => {
    render(<ProductGrid products={[product]} isLoading={false} isError={false} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Articulated Dragon/ })).toBeInTheDocument();
  });

  it("Batch 3: loading shows card-shaped placeholders inside one announced status, hidden from the reading order", () => {
    const { container } = render(<ProductGrid products={[]} isLoading isError={false} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Loading…");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(container.querySelector("ul")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("Batch 3: the showcase layout goes 4-up at xl, the catalog layout stops at 3-up", () => {
    const { container, rerender } = render(<ProductGrid products={[product]} isLoading={false} isError={false} layout="showcase" />);
    expect(container.querySelector("ul")).toHaveClass("xl:grid-cols-4");
    rerender(<ProductGrid products={[product]} isLoading={false} isError={false} />);
    expect(container.querySelector("ul")).toHaveClass("xl:grid-cols-3");
    expect(container.querySelector("ul")).not.toHaveClass("xl:grid-cols-4");
  });
});
