import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProductCard } from "./ProductCard";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

// Phase 6D: the wishlist heart needs the auth context; it has its own tests
// (src/components/wishlist), so it is stubbed out of these card tests.
// The stub is a real control so the no-nesting rule below can be checked.
vi.mock("@/components/wishlist/WishlistButton", () => ({
  WishlistButton: ({ productName, returnToPath }: { productName: string; returnToPath: string }) => (
    <button type="button" data-return-to={returnToPath}>
      Save {productName} to your wishlist
    </button>
  ),
}));

const baseProduct: ProductCardModel = {
  id: "p1",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  coverImage: { src: "/media/products/dragon.png", alt: "Articulated Dragon, view 1" },
  price: { amountCents: 1800, currency: "USD" },
  promotion: null,
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

  it("with no promotion, shows one price and no discount badge", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/^-\d/)).toBeNull();
    expect(document.querySelector("s")).toBeNull();
  });

  it("with a server promotion, shows the badge, the current price and the original struck through, in words too", () => {
    render(
      <ProductCard
        product={{
          ...baseProduct,
          price: { amountCents: 1440, currency: "USD" },
          promotion: {
            id: "promo-1",
            name: "Eid Sale",
            badgeText: null,
            discountType: "percentage",
            discountValue: 20,
            endsAt: "2026-12-20T00:00:00Z",
            listPrice: { amountCents: 1800, currency: "USD" },
          },
        }}
      />
    );
    expect(screen.getByText("-20%")).toBeInTheDocument();
    expect(screen.getByText("$14.40")).toBeInTheDocument();
    expect(screen.getByText("$18.00").closest("s")).not.toBeNull();
    const link = screen.getByRole("link");
    expect(link).toHaveTextContent(/Current promotional price:\s*\$14\.40/);
    expect(link).toHaveTextContent(/Original price:\s*\$18\.00/);
    expect(link).toHaveTextContent(/Eid Sale/);
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
    // Phase 6E: AA contrast on the warning tint.
    expect(screen.getByText(/unavailable/i)).toHaveClass("text-on-warning-container");
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

  it("never renders a star rating while there are no reviews (review_count 0)", () => {
    const { container } = render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/★|☆|review|rated/i)).not.toBeInTheDocument();
    expect(container.querySelector("[data-icon=star]")).toBeNull();
  });

  it("renders the real rating only when review_count is above zero, with a spoken summary", () => {
    render(<ProductCard product={{ ...baseProduct, averageRating: 4.5, reviewCount: 12 }} />);
    expect(screen.getByRole("link")).toHaveAccessibleName(/Rated 4\.5 out of 5 from 12 reviews/);
  });

  it("never renders a stock quantity — no such field exists in the contract", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.queryByText(/in stock|stock:/i)).not.toBeInTheDocument();
  });

  it("the card link holds the image, name, price and a View details call to action — and no nested control", () => {
    render(<ProductCard product={baseProduct} />);
    const link = screen.getByRole("link");
    expect(link).toHaveTextContent("View details");
    expect(link).toContainElement(screen.getByRole("img", { name: "Articulated Dragon, view 1" }));
    expect(link.querySelector("a, button, input, select, textarea")).toBeNull();
  });

  it("renders the wishlist heart as a sibling of the card link (never inside it), with the product page as returnTo", () => {
    render(<ProductCard product={baseProduct} />);
    const heart = screen.getByRole("button", { name: "Save Articulated Dragon to your wishlist" });
    expect(screen.getByRole("link")).not.toContainElement(heart);
    expect(heart).toHaveAttribute("data-return-to", "/shop/dragon");
  });

  it("uses the real cover image with its alt text, cropped to a square (never tiled)", () => {
    render(<ProductCard product={baseProduct} />);
    const img = screen.getByRole("img", { name: "Articulated Dragon, view 1" });
    expect(img).toHaveAttribute("src", "/media/products/dragon.png");
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveClass("object-cover");
    expect(img.parentElement).toHaveClass("aspect-square");
  });

  it("turns its hover zoom and lift off under prefers-reduced-motion", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.getByRole("img")).toHaveClass("motion-reduce:transition-none", "motion-reduce:group-hover:scale-100");
    expect(screen.getByRole("link").parentElement).toHaveClass("motion-reduce:transition-none", "motion-reduce:hover:translate-y-0");
  });

  it("shows the category name on the card", () => {
    render(<ProductCard product={baseProduct} />);
    expect(screen.getByText("Toys and Figures")).toBeInTheDocument();
  });

  it("keeps the full product name in the heading even when it is visually clamped", () => {
    const longName = "Articulated Dragon With Extra Long Tail And Fully Posable Wings, Limited Desk Edition";
    render(<ProductCard product={{ ...baseProduct, name: longName }} />);
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveTextContent(longName);
    expect(heading).toHaveClass("line-clamp-2");
  });
});
