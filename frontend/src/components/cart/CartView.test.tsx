import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CartView } from "./CartView";
import { cartApi } from "@/lib/cart/cartApi";
import type { CartLineReadDTO, CartReadDTO } from "@/lib/cart/cartTypes";

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
const mockedUseAuth = vi.mocked(useAuth);

function signedIn({ verified = true, isError = false } = {}) {
  mockedUseAuth.mockReturnValue({
    user: isError
      ? null
      : { id: "u-1", email: "a@b.c", role: "customer", emailVerified: verified, emailVerifiedAt: null, createdAt: "" },
    isAuthenticated: !isError,
    isLoading: false,
    isError,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
}

const PHYSICAL: CartLineReadDTO = {
  product_id: "p-1",
  product_type: "physical",
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
const STL: CartLineReadDTO = {
  ...PHYSICAL,
  product_id: "p-2",
  product_type: "stl",
  name: "Knight STL",
  slug: "knight-stl",
  quantity: 1,
  max_quantity: null,
};
function cartOf(items: CartLineReadDTO[]): CartReadDTO {
  return {
    id: items.length ? "c-1" : null,
    items,
    contains_physical: items.some((i) => i.product_type === "physical"),
    contains_digital: items.some((i) => i.product_type === "stl"),
    updated_at: null,
  };
}

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <CartView />
    </QueryClientProvider>
  );
  return { queryClient };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CartView", () => {
  it("renders the page heading and the server's lines", async () => {
    signedIn();
    vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([PHYSICAL, STL]));
    renderView();
    expect(screen.getByRole("heading", { level: 1, name: "Your cart" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Dragon" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Knight STL" })).toBeInTheDocument();
  });

  it("shows the empty state for a never-written cart", async () => {
    signedIn();
    vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([]));
    renderView();
    expect(await screen.findByText("Your cart is empty.")).toBeInTheDocument();
  });

  it("shows a retryable error and retries the read", async () => {
    signedIn();
    const getSpy = vi
      .spyOn(cartApi, "getCart")
      .mockRejectedValueOnce({ kind: "network", message: "x", raw: null })
      .mockResolvedValueOnce(cartOf([]));
    const user = userEvent.setup();
    renderView();
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Your cart is empty.")).toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(2);
  });

  it("increase sends PATCH with the absolute quantity, keeps controls disabled while pending, then shows the server's answer", async () => {
    signedIn();
    let resolvePatch: (value: CartReadDTO) => void = () => {};
    const patchSpy = vi
      .spyOn(cartApi, "setItemQuantity")
      .mockReturnValue(new Promise((resolve) => (resolvePatch = resolve)));
    const getSpy = vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([PHYSICAL]));
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Increase quantity of Dragon" }));
    expect(patchSpy).toHaveBeenCalledWith("p-1", 3);
    expect(screen.getByRole("button", { name: "Increase quantity of Dragon" })).toBeDisabled();
    // Not optimistic: still the server's 2 while pending.
    expect(within(screen.getByRole("group", { name: "Quantity of Dragon" })).getByText("2")).toBeInTheDocument();

    const updated = cartOf([{ ...PHYSICAL, quantity: 3 }]);
    getSpy.mockResolvedValue(updated);
    resolvePatch(updated);
    await waitFor(() =>
      expect(within(screen.getByRole("group", { name: "Quantity of Dragon" })).getByText("3")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "Increase quantity of Dragon" })).toBeEnabled();
  });

  it("a refused quantity shows the server-derived limit on that line and refetches", async () => {
    signedIn();
    vi.spyOn(cartApi, "setItemQuantity").mockRejectedValue({
      kind: "http",
      status: 422,
      code: "QUANTITY_EXCEEDS_LIMIT",
      message: "x",
      raw: { code: "QUANTITY_EXCEEDS_LIMIT", max_quantity: 2, requested: 3, current_quantity: 2 },
    });
    const getSpy = vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([PHYSICAL]));
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Increase quantity of Dragon" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You can have at most 2 of this product in your cart. You already have 2."
    );
    await waitFor(() => expect(getSpy).toHaveBeenCalledTimes(2));
  });

  it("remove sends DELETE by product id, refetches, and moves focus to the heading", async () => {
    signedIn();
    const delSpy = vi.spyOn(cartApi, "removeItem").mockResolvedValue(undefined);
    const getSpy = vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([PHYSICAL, STL]));
    const user = userEvent.setup();
    renderView();

    await screen.findByRole("link", { name: "Knight STL" });
    getSpy.mockResolvedValue(cartOf([PHYSICAL]));
    await user.click(screen.getByRole("button", { name: "Remove Knight STL from cart" }));

    expect(delSpy).toHaveBeenCalledWith("p-2");
    await waitFor(() => expect(screen.queryByRole("link", { name: "Knight STL" })).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 1, name: "Your cart" })).toHaveFocus();
  });

  it("removing the last line ends on the empty state", async () => {
    signedIn();
    vi.spyOn(cartApi, "removeItem").mockResolvedValue(undefined);
    const getSpy = vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([PHYSICAL]));
    const user = userEvent.setup();
    renderView();

    await screen.findByRole("link", { name: "Dragon" });
    getSpy.mockResolvedValue(cartOf([]));
    await user.click(screen.getByRole("button", { name: "Remove Dragon from cart" }));
    expect(await screen.findByText("Your cart is empty.")).toBeInTheDocument();
  });

  it("tells an unverified customer that changes need a verified email", async () => {
    signedIn({ verified: false });
    vi.spyOn(cartApi, "getCart").mockResolvedValue(cartOf([]));
    renderView();
    expect(await screen.findByText(/verify your email address to add or change items/i)).toBeInTheDocument();
  });

  it("an auth-session error shows a retryable error instead of an empty cart", () => {
    signedIn({ isError: true });
    const getSpy = vi.spyOn(cartApi, "getCart");
    renderView();
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load your cart");
    expect(screen.queryByText("Your cart is empty.")).not.toBeInTheDocument();
    expect(getSpy).not.toHaveBeenCalled();
  });
});
