import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HeaderCartLink } from "./HeaderCartLink";
import { cartApi } from "@/lib/cart/cartApi";
import type { CartReadDTO } from "@/lib/cart/cartTypes";

// The header's cart link. The count comes only from the canonical
// GET /cart (shared with /cart and Add to cart): no separate count
// endpoint exists, and none is invented.

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/") }));
vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
import { usePathname } from "next/navigation";
const mockedUseAuth = vi.mocked(useAuth);

function viewer(signedIn: boolean) {
  mockedUseAuth.mockReturnValue({
    user: signedIn
      ? { id: "u-1", email: "a@b.c", role: "customer", emailVerified: true, emailVerifiedAt: null, createdAt: "" }
      : null,
    isAuthenticated: signedIn,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
}

const line = {
  product_id: "p-1",
  product_type: "physical" as const,
  name: "Dragon",
  slug: "dragon",
  cover_image: null,
  quantity: 2,
  snapshot_price: { amount_cents: 2500, currency: "USD" },
  current_price: { amount_cents: 2500, currency: "USD" },
  price_changed: false,
  max_quantity: 5,
  over_cap: false,
  purchasable: true,
  unpurchasable_reason: null,
};

function renderLink() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <HeaderCartLink />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HeaderCartLink", () => {
  it("anonymous: a plain Cart link to /cart and no cart request", () => {
    viewer(false);
    const getSpy = vi.spyOn(cartApi, "getCart");
    renderLink();
    expect(screen.getByRole("link", { name: "Cart" })).toHaveAttribute("href", "/cart");
    expect(getSpy).not.toHaveBeenCalled();
  });

  it("signed in: the unit count from the canonical cart", async () => {
    viewer(true);
    const cart: CartReadDTO = {
      id: "c-1",
      items: [line, { ...line, product_id: "p-2", product_type: "stl", quantity: 1, max_quantity: null }],
      contains_physical: true,
      contains_digital: true,
      updated_at: null,
    };
    vi.spyOn(cartApi, "getCart").mockResolvedValue(cart);
    renderLink();
    expect(await screen.findByRole("link", { name: "Cart, 3 items" })).toHaveAttribute("href", "/cart");
  });

  it("signed in with an empty cart: no badge", async () => {
    viewer(true);
    const getSpy = vi
      .spyOn(cartApi, "getCart")
      .mockResolvedValue({ id: null, items: [], contains_physical: false, contains_digital: false, updated_at: null });
    renderLink();
    await vi.waitFor(() => expect(getSpy).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "Cart" })).toBeInTheDocument();
  });

  it("marks itself current on /cart", () => {
    viewer(false);
    vi.mocked(usePathname).mockReturnValue("/cart");
    renderLink();
    expect(screen.getByRole("link", { name: "Cart" })).toHaveAttribute("aria-current", "page");
  });
});
