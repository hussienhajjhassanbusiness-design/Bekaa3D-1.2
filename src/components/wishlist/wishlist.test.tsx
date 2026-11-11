import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { apiClient } from "@/lib/api/apiClient";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { clearUserScopedQueries } from "@/lib/auth/userScopedQueries";
import { wishlistApi, wishlistKeys, WISHLIST_MAX_PAGES, type WishlistItemDTO } from "@/lib/wishlist/wishlistApi";
import { describeWishlistError, WISHLIST_MESSAGES } from "@/lib/wishlist/useWishlist";
import { WishlistButton } from "./WishlistButton";
import { WishlistList } from "./WishlistList";

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
const mockedUseAuth = vi.mocked(useAuth);

function viewer(state: "anonymous" | "loading" | "unverified" | "verified") {
  const user =
    state === "unverified" || state === "verified"
      ? { id: "u-1", email: "a@b.c", role: "customer", emailVerified: state === "verified", emailVerifiedAt: null, createdAt: "" }
      : null;
  mockedUseAuth.mockReturnValue({ user, isAuthenticated: user !== null, isLoading: state === "loading", isError: false, logout: vi.fn() } as unknown as ReturnType<
    typeof useAuth
  >);
}

function renderWithQuery(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  return client;
}

function http(status: number, code: string): ApiError {
  return { kind: "http", status, code, title: "RAW TITLE", detail: "RAW DETAIL", message: "RAW", raw: { code } };
}

const P1 = "00000000-0000-4000-8000-000000000001";
const P2 = "00000000-0000-4000-8000-000000000002";
const item = (overrides: Partial<WishlistItemDTO> = {}): WishlistItemDTO => ({
  product_id: P1,
  created_at: "2026-11-12T10:00:00Z",
  available: true,
  name: "Dragon STL",
  slug: "dragon-stl",
  type: "stl",
  price_cents: 700,
  currency: "USD",
  ...overrides,
});

afterEach(() => vi.restoreAllMocks());

describe("wishlistApi", () => {
  it("uses the exact routes and CSRF, and follows every page of the list", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ items: [item()], next_cursor: "c1" })
      .mockResolvedValueOnce({ items: [item({ product_id: P2 })], next_cursor: null });
    const put = vi.spyOn(apiClient, "put").mockResolvedValue(undefined);
    const del = vi.spyOn(apiClient, "del").mockResolvedValue(undefined);
    const all = await wishlistApi.listAll();
    await wishlistApi.add(P1);
    await wishlistApi.remove(P1);
    expect(all.map((i) => i.product_id)).toEqual([P1, P2]);
    expect(get.mock.calls).toEqual([["/api/v1/me/wishlist?limit=100"], ["/api/v1/me/wishlist?limit=100&cursor=c1"]]);
    expect(put).toHaveBeenCalledWith(`/api/v1/me/wishlist/${P1}`, undefined, { csrf: true });
    expect(del).toHaveBeenCalledWith(`/api/v1/me/wishlist/${P1}`, { csrf: true });
  });

  it("stops following a cursor after the page cap", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: "again" });
    await wishlistApi.listAll();
    expect(get).toHaveBeenCalledTimes(WISHLIST_MAX_PAGES);
  });

  it("is a user-scoped cache root, dropped on logout and user switch", () => {
    const client = new QueryClient();
    client.setQueryData(wishlistKeys.all(), [item()]);
    clearUserScopedQueries(client);
    expect(client.getQueryData(wishlistKeys.all())).toBeUndefined();
  });

  it("maps refusals to frontend copy only", () => {
    expect(describeWishlistError(http(403, "CSRF_INVALID")).message).toBe(WISHLIST_MESSAGES.csrf);
    expect(describeWishlistError({ kind: "csrf", message: "x", raw: undefined }).message).toBe(WISHLIST_MESSAGES.csrf);
    expect(describeWishlistError(http(403, "EMAIL_VERIFICATION_REQUIRED"))).toEqual({ message: WISHLIST_MESSAGES.verifyEmail, refetchAuth: true });
    expect(describeWishlistError(http(404, "NOT_FOUND")).message).toBe(WISHLIST_MESSAGES.notAvailable);
    expect(describeWishlistError(http(429, "RATE_LIMITED")).message).toBe(WISHLIST_MESSAGES.rateLimited);
    expect(describeWishlistError(http(500, "INTERNAL_ERROR")).message).toBe(WISHLIST_MESSAGES.generic);
  });
});

describe("WishlistButton", () => {
  it("is a sign-in link for an anonymous viewer, with no wishlist request", () => {
    viewer("anonymous");
    const list = vi.spyOn(wishlistApi, "listAll");
    renderWithQuery(<WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/dragon-stl" variant="icon" />);
    expect(screen.getByRole("link", { name: "Sign in to save Dragon STL to your wishlist" })).toHaveAttribute(
      "href",
      buildLoginRedirectPath("/shop/dragon-stl")
    );
    expect(list).not.toHaveBeenCalled();
  });

  it("points an unverified viewer to verification on the product page and hides the card heart", () => {
    viewer("unverified");
    renderWithQuery(
      <>
        <WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/dragon-stl" variant="icon" />
        <WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/dragon-stl" variant="full" />
      </>
    );
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Verify your email" })).toHaveAttribute("href", "/verify-email/resend");
  });

  it("shows the server's state, saves, and re-reads the list before settling", async () => {
    viewer("verified");
    const list = vi.spyOn(wishlistApi, "listAll").mockResolvedValueOnce([]).mockResolvedValueOnce([item()]);
    const add = vi.spyOn(wishlistApi, "add").mockResolvedValue(undefined);
    renderWithQuery(<WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/dragon-stl" variant="icon" />);
    const heart = await screen.findByRole("button", { name: "Save Dragon STL to your wishlist" });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    await userEvent.setup().click(heart);
    await waitFor(() => expect(heart).toHaveAttribute("aria-pressed", "true"));
    expect(add).toHaveBeenCalledWith(P1);
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("keeps the state and shows safe copy on a refusal", async () => {
    viewer("verified");
    vi.spyOn(wishlistApi, "listAll").mockResolvedValue([item()]);
    vi.spyOn(wishlistApi, "remove").mockRejectedValue(http(403, "CSRF_INVALID"));
    renderWithQuery(<WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/dragon-stl" variant="full" />);
    const button = await screen.findByRole("button", { name: "Remove from wishlist" });
    expect(screen.getByRole("status")).toHaveTextContent("Saved to your wishlist.");
    await userEvent.setup().click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent(WISHLIST_MESSAGES.csrf);
    expect(screen.getByRole("button", { name: "Remove from wishlist" })).toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).toBeNull();
  });

  it("serves every heart on a page from one list read", async () => {
    viewer("verified");
    const list = vi.spyOn(wishlistApi, "listAll").mockResolvedValue([item()]);
    renderWithQuery(
      <>
        <WishlistButton productId={P1} productName="Dragon STL" returnToPath="/shop/a" variant="icon" />
        <WishlistButton productId={P2} productName="Vase" returnToPath="/shop/b" variant="icon" />
      </>
    );
    expect(await screen.findByRole("button", { name: "Save Dragon STL to your wishlist" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Save Vase to your wishlist" })).toHaveAttribute("aria-pressed", "false");
    expect(list).toHaveBeenCalledTimes(1);
  });
});

describe("WishlistList", () => {
  it("shows the empty state", async () => {
    viewer("verified");
    vi.spyOn(wishlistApi, "listAll").mockResolvedValue([]);
    renderWithQuery(<WishlistList />);
    expect(await screen.findByText(/Your wishlist is empty/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");
  });

  it("lists items, keeps an unavailable one by name, and removes through the server", async () => {
    viewer("verified");
    vi.spyOn(wishlistApi, "listAll")
      .mockResolvedValueOnce([item(), item({ product_id: P2, available: false, name: "Old vase", slug: null, type: null, price_cents: null, currency: null })])
      .mockResolvedValueOnce([item({ product_id: P2, available: false, name: "Old vase", slug: null, type: null, price_cents: null, currency: null })]);
    const remove = vi.spyOn(wishlistApi, "remove").mockResolvedValue(undefined);
    renderWithQuery(<WishlistList />);
    expect(await screen.findByRole("link", { name: "Dragon STL" })).toHaveAttribute("href", "/shop/dragon-stl");
    expect(screen.getByText("$7.00")).toBeInTheDocument();
    const old = screen.getByText("Old vase").closest("li")!;
    expect(within(old).getByText("No longer available")).toBeInTheDocument();
    expect(within(old).queryByRole("link")).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove Dragon STL from your wishlist" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Removed Dragon STL from your wishlist.");
    expect(remove).toHaveBeenCalledWith(P1);
    expect(screen.queryByRole("link", { name: "Dragon STL" })).toBeNull();
  });

  it("shows a retryable error", async () => {
    viewer("verified");
    const list = vi.spyOn(wishlistApi, "listAll").mockRejectedValueOnce(http(500, "INTERNAL_ERROR")).mockRejectedValueOnce(http(500, "INTERNAL_ERROR")).mockResolvedValueOnce([]);
    renderWithQuery(<WishlistList />);
    // A 5xx is retried once automatically before the error is shown.
    await userEvent.setup().click(await screen.findByRole("button", { name: "Try again" }, { timeout: 4000 }));
    expect(await screen.findByText(/Your wishlist is empty/)).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(3);
  });
});
