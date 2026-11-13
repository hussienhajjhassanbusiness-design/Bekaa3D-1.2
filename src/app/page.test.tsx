import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import Home from "./page";

// Phase 6D: the wishlist heart needs the auth context; it has its own tests
// (src/components/wishlist), so it is stubbed out of these card tests.
vi.mock("@/components/wishlist/WishlistButton", () => ({ WishlistButton: () => null }));

// REAL STOREFRONT INTEGRATION — PHASE 1: Home now composes HeroSection
// (with real /shop, /about CTAs), FeaturedProductsSection,
// CategoryShowcaseSection, and WhyChooseSection, instead of the
// Hero-only placeholder. The AppLayout/Header/Footer shell is owned by
// the root layout (see src/app/layout.test.tsx) — this file tests only
// Home's own page content.

function renderHome() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <Home />
    </QueryClientProvider>
  );
}

function mockApi({ hasFeatured = true, hasCategories = true } = {}) {
  vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
    const p = path as string;
    if (p.startsWith("/api/v1/categories")) {
      return { items: hasCategories ? [{ id: "cat-1", name: "Toys", slug: "toys" }] : [] };
    }
    if (p.startsWith("/api/v1/products")) {
      return {
        items: hasFeatured
          ? [
              {
                id: "p1",
                type: "physical",
                name: "Articulated Dragon",
                slug: "dragon",
                cover_image: null,
                price: { amount_cents: 1800, currency: "USD" },
                category: { id: "cat-1", name: "Toys", slug: "toys" },
                material: null,
                colour: null,
                is_available: true,
                purchase_mode: "both",
                average_rating: 0,
                review_count: 0,
                is_featured: true,
              },
            ]
          : [],
        next_cursor: null,
      };
    }
    throw new Error(`unexpected path: ${p}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Home (root route /)", () => {
  it("renders the approved Bekaa3D heading via HeroSection", () => {
    mockApi();
    renderHome();

    expect(
      screen.getByRole("heading", { level: 1, name: /Bekaa3D — Engineered Grade 3D Solutions/i })
    ).toBeInTheDocument();
  });

  it("no longer renders the retired FVS-001 placeholder paragraph", () => {
    mockApi();
    renderHome();

    expect(screen.queryByText(/foundation slice/i)).not.toBeInTheDocument();
  });

  it("renders real CTAs to the now-mounted /shop and /about routes", () => {
    mockApi();
    renderHome();

    expect(screen.getByRole("link", { name: "Shop Now" })).toHaveAttribute("href", "/shop");
    expect(screen.getByRole("link", { name: "Learn More" })).toHaveAttribute("href", "/about");
  });

  it("renders the Why Choose Bekaa3D static brand section", () => {
    mockApi();
    renderHome();

    expect(screen.getByRole("heading", { name: "Why Choose Bekaa3D" })).toBeInTheDocument();
  });

  it("renders real featured products when the backend returns some", async () => {
    mockApi({ hasFeatured: true });
    renderHome();

    expect(await screen.findByRole("link", { name: /Articulated Dragon/ })).toBeInTheDocument();
  });

  it("omits the featured-products section entirely when there are none — never a fake placeholder grid", async () => {
    mockApi({ hasFeatured: false });
    renderHome();

    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Featured Products" })).not.toBeInTheDocument());
  });

  it("omits the category showcase entirely when there are no categories", async () => {
    mockApi({ hasCategories: false });
    renderHome();

    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Shop by Category" })).not.toBeInTheDocument());
  });

  it("confines the hero's decorative markup to exactly one aria-hidden wrapper, separate from the real heading", () => {
    mockApi();
    const { container } = renderHome();

    const heroWrapper = container.querySelector(".relative.overflow-hidden");
    expect(heroWrapper).not.toBeNull();
    const wrappers = heroWrapper!.querySelectorAll(':scope > [aria-hidden="true"]');
    expect(wrappers).toHaveLength(1);
    const wrapper = wrappers[0]!;

    const heading = screen.getByRole("heading", { level: 1 });
    expect(wrapper.contains(heading)).toBe(false);

    const decorativeChildren = wrapper.querySelectorAll("div");
    expect(decorativeChildren.length).toBeGreaterThan(0);
  });

  it("Batch 3: real sections in Stitch order with one h1 and h2 section headings", async () => {
    mockApi();
    renderHome();

    expect(await screen.findByRole("heading", { level: 2, name: "Shop by Category" })).toBeInTheDocument();
    await screen.findByRole("heading", { level: 2, name: "Featured Products" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Shop by Category",
      "Featured Products",
      "Why Choose Bekaa3D",
      "Have something in mind that isn’t in the shop?".replace("’", "'"),
    ]);
  });

  it("Batch 3: every new home link goes to a real route", async () => {
    mockApi();
    renderHome();

    expect(await screen.findByRole("link", { name: /Shop all products/ })).toHaveAttribute("href", "/shop");
    expect(await screen.findByRole("link", { name: /View all products/ })).toHaveAttribute("href", "/shop");
    expect(screen.getByRole("link", { name: "Bring your idea" })).toHaveAttribute("href", "/bring-your-idea");
    expect(screen.getByRole("link", { name: "Contact us" })).toHaveAttribute("href", "/contact");
  });

  it("Batch 3: category tiles link to the shop filtered by the real category id", async () => {
    mockApi();
    renderHome();

    const section = (await screen.findByRole("heading", { name: "Shop by Category" })).closest("section")!;
    const categoryLinks = Array.from(section.querySelectorAll("a")).filter((a) => a.getAttribute("href")!.includes("category="));
    expect(categoryLinks.length).toBeGreaterThan(0);
    for (const link of categoryLinks) expect(link.getAttribute("href")).toMatch(/^\/shop\?category=/);
  });

  it("Batch 3: no invented statistics, testimonials, promotions or discounts", async () => {
    mockApi();
    renderHome();

    await screen.findByRole("heading", { name: "Featured Products" });
    expect(screen.queryByText(/models shipped|tolerance|testimonial|trusted by|% off|discount|redeem/i)).not.toBeInTheDocument();
  });
});
