import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import { HomePromotionBanner } from "./HomePromotionBanner";
import type { PublicPromotionRead } from "@/lib/promotions/promotionTypes";

const EID: PublicPromotionRead = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Eid Sale",
  badge_text: "Eid al-Fitr",
  discount_type: "percentage",
  discount_value: 20,
  scope: "all",
  starts_at: "2026-12-01T00:00:00Z",
  ends_at: "2026-12-20T00:00:00Z",
};

function cover(url: string) {
  return { cover_image: { id: url, url, alt_text: "A real product", is_cover: true } };
}

function mockApi(promotions: readonly PublicPromotionRead[] | Error, products: unknown[] = []) {
  return vi.spyOn(apiClient, "get").mockImplementation(async (path: unknown) => {
    if (path === "/api/v1/promotions") {
      if (promotions instanceof Error) throw promotions;
      return { items: promotions };
    }
    return { items: products, next_cursor: null };
  });
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <h1>Home</h1>
      <HomePromotionBanner />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HomePromotionBanner", () => {
  it("renders the server's active promotion with a truthful CTA to its products", async () => {
    mockApi([EID]);
    renderBanner();

    const heading = await screen.findByRole("heading", { level: 2, name: /20% OFF\s*Eid Sale/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("Eid al-Fitr")).toBeInTheDocument();
    expect(screen.getByText(/Save 20% on everything in the shop until/)).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /shop promotion/i });
    expect(cta).toHaveAttribute("href", `/shop?promotion=${EID.id}`);
    expect(screen.queryByText(/redeem/i)).toBeNull();
  });

  it("labels a fixed discount from its cents", async () => {
    mockApi([{ ...EID, discount_type: "fixed", discount_value: 500, scope: "stl", badge_text: null }]);
    renderBanner();
    expect(await screen.findByRole("heading", { level: 2, name: /\$5 OFF\s*Eid Sale/ })).toBeInTheDocument();
    expect(screen.getByText(/Save \$5 on STL files until/)).toBeInTheDocument();
  });

  it("renders nothing at all when no promotion is active — no placeholder campaign", async () => {
    const get = mockApi([]);
    const { container } = renderBanner();
    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/v1/promotions"));
    expect(container.querySelector("section")).toBeNull();
    expect(screen.queryByText(/OFF/)).toBeNull();
    expect(screen.queryByText(/Storewide Launch/i)).toBeNull();
  });

  it("renders nothing when the promotions read fails", async () => {
    const get = mockApi(new Error("network"));
    const { container } = renderBanner();
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(container.querySelector("section")).toBeNull();
  });

  it("shows covered products' real cover images as decorative imagery", async () => {
    const get = mockApi([EID], [cover("/media/a.png"), cover("/media/b.png")]);
    const { container } = renderBanner();
    await screen.findByRole("heading", { level: 2 });
    await waitFor(() => expect(container.querySelectorAll("img")).toHaveLength(2));
    expect(get).toHaveBeenCalledWith(expect.stringContaining(`promotion_id=${EID.id}`));
    for (const img of container.querySelectorAll("img")) {
      expect(img).toHaveAttribute("alt", "");
      expect(img.getAttribute("src")).not.toMatch(/googleusercontent|lh3\.google/);
    }
    expect(container.querySelector('[aria-hidden="true"] img')).not.toBeNull();
  });

  it("keeps one h1 on the page: the banner heading is an h2", async () => {
    mockApi([EID]);
    renderBanner();
    await screen.findByRole("heading", { level: 2 });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
