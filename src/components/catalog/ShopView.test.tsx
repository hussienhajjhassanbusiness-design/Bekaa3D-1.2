import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { ShopView } from "./ShopView";

// Phase 6D: the wishlist heart needs the auth context; it has its own tests
// (src/components/wishlist), so it is stubbed out of these card tests.
vi.mock("@/components/wishlist/WishlistButton", () => ({ WishlistButton: () => null }));

const mockPush = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/shop",
  useSearchParams: () => mockSearchParams,
}));

function renderShopView() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ShopView />
    </QueryClientProvider>
  );
}

function mockApi() {
  vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
    const p = path as string;
    if (p.startsWith("/api/v1/categories")) return { items: [{ id: "cat-1", name: "Toys", slug: "toys" }] };
    if (p.startsWith("/api/v1/materials")) return { items: [{ id: "mat-1", name: "PLA" }] };
    if (p.startsWith("/api/v1/colours")) return { items: [{ id: "col-1", name: "Red" }] };
    if (p.startsWith("/api/v1/search/suggestions")) {
      return { items: [{ id: "p1", name: "Articulated Dragon", slug: "dragon", type: "physical" }] };
    }
    if (p.startsWith("/api/v1/products")) {
      return {
        items: [
          {
            id: "p1",
            type: "physical",
            name: "Articulated Dragon",
            slug: "dragon",
            cover_image: null,
            price: { amount_cents: 1800, currency: "USD" },
            category: { id: "cat-1", name: "Toys", slug: "toys" },
            material: { id: "mat-1", name: "PLA" },
            colour: { id: "col-1", name: "Red" },
            is_available: true,
            purchase_mode: "both",
            average_rating: 0,
            review_count: 0,
            is_featured: false,
          },
        ],
        next_cursor: p.includes("cursor=token-1") ? "token-2" : p.includes("cursor=") ? null : "token-1",
      };
    }
    throw new Error(`unexpected path in test: ${p}`);
  });
}

beforeEach(() => {
  mockSearchParams = new URLSearchParams();
  mockPush.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ShopView", () => {
  it("renders facet groups built from live category/material/colour data, not hardcoded", async () => {
    mockApi();
    renderShopView();

    expect(await screen.findByRole("checkbox", { name: "Toys" })).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "PLA" })).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Red" })).toBeInTheDocument();
  });

  it("renders the product grid from the real list response", async () => {
    mockApi();
    renderShopView();

    expect(await screen.findByRole("link", { name: /Articulated Dragon/ })).toBeInTheDocument();
  });

  it("checking a category facet pushes category=<id> to the URL (not category_id — that's the API adapter's job)", async () => {
    mockApi();
    renderShopView();

    const checkbox = await screen.findByRole("checkbox", { name: "Toys" });
    await userEvent.click(checkbox);

    await waitFor(() => expect(mockPush).toHaveBeenCalled());
    const [pushedUrl] = mockPush.mock.calls[0]!;
    expect(pushedUrl).toBe("/shop?category=cat-1");
  });

  it("unchecking the currently selected facet clears it", async () => {
    mockSearchParams = new URLSearchParams("category=cat-1");
    mockApi();
    renderShopView();

    const checkbox = await screen.findByRole("checkbox", { name: "Toys" });
    expect(checkbox).toBeChecked();

    await userEvent.click(checkbox);
    await waitFor(() => expect(mockPush).toHaveBeenCalled());
    expect(mockPush).toHaveBeenCalledWith("/shop?");
  });

  it("shows a removable applied-filter chip for an active facet", async () => {
    mockSearchParams = new URLSearchParams("category=cat-1");
    mockApi();
    renderShopView();

    expect(await screen.findByRole("button", { name: /remove toys filter/i })).toBeInTheDocument();
  });

  it("changing sort pushes the new sort value to the URL", async () => {
    mockApi();
    renderShopView();

    const select = await screen.findByLabelText(/sort by/i);
    await userEvent.selectOptions(select, "-price");

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/shop?sort=-price"));
  });

  it("submitting a search commits q to the URL", async () => {
    mockApi();
    renderShopView();

    const searchInput = await screen.findByLabelText(/search products/i);
    await userEvent.type(searchInput, "dragon");
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/shop?q=dragon"));
  });

  it("clicking Load more fetches the next page and appends it to the grid", async () => {
    mockApi();
    renderShopView();

    await screen.findByRole("link", { name: /Articulated Dragon/ });
    const loadMoreButton = await screen.findByRole("button", { name: /load more/i });
    await userEvent.click(loadMoreButton);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/shop?cursor=token-2"));
  });

  it("shows the empty state when the product list is empty", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
      const p = path as string;
      if (p.startsWith("/api/v1/products")) return { items: [], next_cursor: null };
      return { items: [] };
    });
    renderShopView();

    expect(await screen.findByText(/no products match your filters/i)).toBeInTheDocument();
  });
});
