import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { FeaturedProductsSection } from "./FeaturedProductsSection";

// Phase 6D: the wishlist heart needs the auth context; it has its own tests
// (src/components/wishlist), so it is stubbed out of these card tests.
vi.mock("@/components/wishlist/WishlistButton", () => ({ WishlistButton: () => null }));

function renderSection() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <FeaturedProductsSection />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FeaturedProductsSection", () => {
  it("calls GET /api/v1/products?featured=true — the real, confirmed query parameter", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });

    renderSection();

    await waitFor(() => expect(getSpy).toHaveBeenCalled());
    const [calledPath] = getSpy.mock.calls[0]!;
    expect(calledPath).toContain("featured=true");
  });

  it("shows the loading skeleton while pending", () => {
    vi.spyOn(apiClient, "get").mockImplementation(() => new Promise(() => {}));

    renderSection();

    expect(screen.getByRole("heading", { name: "Featured Products" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it(
    "omits the whole section on a fetch failure — never a broken home-page section",
    async () => {
      vi.spyOn(apiClient, "get").mockRejectedValue({ kind: "network", message: "x", raw: undefined });

      renderSection();

      await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
      // useProducts retries transient failures with TanStack's default
      // backoff before settling into isError — this section is a
      // "nice to have" homepage extra, so the test simply allows enough
      // real time for that default retry sequence to finish.
      await waitFor(
        () => expect(screen.queryByRole("heading", { name: "Featured Products" })).not.toBeInTheDocument(),
        { timeout: 10_000 }
      );
    },
    15_000
  );

  it("renders real featured products when the backend returns some", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      items: [
        {
          id: "p1",
          type: "physical",
          name: "Moon Lamp",
          slug: "moon-lamp",
          cover_image: null,
          price: { amount_cents: 2500, currency: "USD" },
          category: { id: "c1", name: "Home Decor", slug: "home-decor" },
          material: null,
          colour: null,
          is_available: true,
          purchase_mode: "both",
          average_rating: 0,
          review_count: 0,
          is_featured: true,
        },
      ],
      next_cursor: null,
    });

    renderSection();

    expect(await screen.findByRole("link", { name: /Moon Lamp/ })).toBeInTheDocument();
  });
});
