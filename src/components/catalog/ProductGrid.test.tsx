import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductGrid } from "./ProductGrid";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

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
});
