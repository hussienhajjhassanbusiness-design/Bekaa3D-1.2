import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProductCard } from "./ProductCard";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

const baseProduct: ProductCardModel = {
  id: "p1",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  coverImage: { src: "/media/products/dragon.png", alt: "Articulated Dragon, view 1" },
  price: { amountCents: 1800, currency: "USD" },
  category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
  material: { id: "m1", name: "PLA" },
  colour: { id: "co1", name: "Red" },
  isAvailable: true,
  purchaseMode: "both",
  averageRating: 0,
  reviewCount: 0,
  isFeatured: false,
};

describe("ProductCard", () => {
  it("renders as a single link to /shop/{slug} with the product name as its accessible name", () => {
    render(<ProductCard product={baseProduct} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/shop/dragon");
    expect(link).toHaveAccessibleName(/Articulated Dragon/);
  });

  it("shows the price via PriceDisplay", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.getByText("$18.00")).toBeInTheDocument();
  });

  it("shows the product type badge", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.getByText("Physical")).toBeInTheDocument();
  });

  it("shows an STL badge for an STL product", () => {
    render(<ProductCard product={{ ...baseProduct, type: "stl" }} />);
    expect(screen.getByText("STL")).toBeInTheDocument();
  });

  it("shows a placeholder, never a broken image, when coverImage is null", () => {
    render(<ProductCard product={{ ...baseProduct, coverImage: null }} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/no image available/i)).toBeInTheDocument();
  });

  it("shows an Unavailable badge when the product is not available", () => {
    render(<ProductCard product={{ ...baseProduct, isAvailable: false }} />);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });

  it("does not show an Unavailable badge for an available product", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
  });

  it("shows a Featured badge only when is_featured is true", () => {
    const { rerender } = render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/featured/i)).not.toBeInTheDocument();

    rerender(<ProductCard product={{ ...baseProduct, isFeatured: true }} />);
    expect(screen.getByText(/featured/i)).toBeInTheDocument();
  });

  it("never renders a star rating — reviews are always zero until VS-036 ships", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/★|☆|review/i)).not.toBeInTheDocument();
  });

  it("never renders a stock quantity — no such field exists in the contract", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/in stock|stock:/i)).not.toBeInTheDocument();
  });
});
