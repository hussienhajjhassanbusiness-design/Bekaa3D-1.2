import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AddToCartButton, type AddToCartButtonProps } from "./AddToCartButton";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { cartApi } from "@/lib/cart/cartApi";
import type { CartReadDTO } from "@/lib/cart/cartTypes";

// Phase 5C (FVS-025) — the product page's real Add to cart.
// POST /api/v1/cart/items `{product_id, quantity}`. Shown only when the
// ProductDetail says `capabilities.can_add_to_cart`; the backend still
// applies the same rule plus per-customer ones (STL ownership, caps).

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
const mockedUseAuth = vi.mocked(useAuth);

function viewer(state: "anonymous" | "loading" | "unverified" | "verified") {
  const user =
    state === "unverified" || state === "verified"
      ? { id: "u-1", email: "a@b.c", role: "customer", emailVerified: state === "verified", emailVerifiedAt: null, createdAt: "" }
      : null;
  mockedUseAuth.mockReturnValue({
    user,
    isAuthenticated: user !== null,
    isLoading: state === "loading",
    isError: false,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
}

const CART: CartReadDTO = { id: "c-1", items: [], contains_physical: true, contains_digital: false, updated_at: null };

const PHYSICAL: AddToCartButtonProps = {
  productId: "p-1",
  productType: "physical",
  productName: "Dragon",
  canAddToCart: true,
  maxQuantityPerLine: 3,
  returnToPath: "/shop/dragon",
};
const STL: AddToCartButtonProps = {
  ...PHYSICAL,
  productId: "p-2",
  productType: "stl",
  productName: "Dragon STL",
  maxQuantityPerLine: null,
};

function renderButton(props: AddToCartButtonProps = PHYSICAL) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AddToCartButton {...props} />
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AddToCartButton", () => {
  it("anonymous: a login-redirect link built by the shared returnTo helper, and no request", () => {
    viewer("anonymous");
    const addSpy = vi.spyOn(cartApi, "addItem");
    renderButton();
    expect(screen.getByRole("link", { name: "Add to cart" })).toHaveAttribute(
      "href",
      buildLoginRedirectPath("/shop/dragon")
    );
    expect(addSpy).not.toHaveBeenCalled();
  });

  it("renders nothing while the session is still resolving", () => {
    viewer("loading");
    renderButton();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders nothing and sends nothing when can_add_to_cart is false (e.g. WhatsApp-only)", () => {
    viewer("verified");
    const addSpy = vi.spyOn(cartApi, "addItem");
    renderButton({ ...PHYSICAL, canAddToCart: false });
    expect(screen.queryByRole("button", { name: "Add to cart" })).not.toBeInTheDocument();
    expect(addSpy).not.toHaveBeenCalled();
  });

  it("unverified: explains and links to resend verification instead of sending a doomed request", () => {
    viewer("unverified");
    renderButton();
    expect(screen.queryByRole("button", { name: "Add to cart" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verify your email/i })).toHaveAttribute("href", "/verify-email/resend");
  });

  it("physical: sends the exact body with the chosen quantity, bounded by max_quantity_per_line", async () => {
    viewer("verified");
    const addSpy = vi.spyOn(cartApi, "addItem").mockResolvedValue(CART);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const user = userEvent.setup();
    renderButton();

    const increase = screen.getByRole("button", { name: "Increase quantity" });
    await user.click(increase);
    await user.click(increase);
    expect(increase).toBeDisabled();
    expect(screen.getByText("Maximum 3 per order")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to cart" }));

    expect(addSpy).toHaveBeenCalledWith({ product_id: "p-1", quantity: 3 });
    expect(await screen.findByRole("status")).toHaveTextContent("Added to your cart.");
    expect(screen.getByRole("link", { name: "View cart" })).toHaveAttribute("href", "/cart");
  });

  it("physical: decrease cannot go below 1", () => {
    viewer("verified");
    renderButton();
    expect(screen.getByRole("button", { name: "Decrease quantity" })).toBeDisabled();
  });

  it("STL: no quantity control; always sends quantity 1", async () => {
    viewer("verified");
    const addSpy = vi.spyOn(cartApi, "addItem").mockResolvedValue(CART);
    vi.spyOn(cartApi, "getCart").mockResolvedValue(CART);
    const user = userEvent.setup();
    renderButton(STL);

    expect(screen.queryByRole("button", { name: /quantity/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to cart" }));
    expect(addSpy).toHaveBeenCalledWith({ product_id: "p-2", quantity: 1 });
  });

  it("is disabled while the request is pending (no double add)", async () => {
    viewer("verified");
    const addSpy = vi.spyOn(cartApi, "addItem").mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderButton(STL);

    await user.click(screen.getByRole("button", { name: "Add to cart" }));
    const busy = screen.getByRole("button", { name: /adding/i });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(addSpy).toHaveBeenCalledTimes(1);
  });

  it("shows frontend-owned copy for a refused add, never the server's detail", async () => {
    viewer("verified");
    vi.spyOn(cartApi, "addItem").mockRejectedValue({
      kind: "http",
      status: 409,
      code: "PRODUCT_ALREADY_OWNED",
      detail: "RAW DETAIL",
      message: "x",
      raw: { code: "PRODUCT_ALREADY_OWNED", detail: "RAW DETAIL", product_ids: ["p-2"] },
    });
    const user = userEvent.setup();
    renderButton(STL);

    await user.click(screen.getByRole("button", { name: "Add to cart" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("You already own this STL file");
    expect(alert).not.toHaveTextContent("RAW");
  });
});
