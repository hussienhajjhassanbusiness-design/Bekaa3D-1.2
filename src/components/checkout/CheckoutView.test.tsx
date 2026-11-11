import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { addressesApi } from "@/lib/addresses/addressesApi";
import type { AddressReadDTO } from "@/lib/addresses/addressTypes";
import { cartApi } from "@/lib/cart/cartApi";
import type { CartLineReadDTO, CartReadDTO } from "@/lib/cart/cartTypes";
import { checkoutApi } from "@/lib/checkout/checkoutApi";
import { CHECKOUT_MESSAGES } from "@/lib/checkout/checkoutErrors";
import { CONSENT_COPY } from "@/lib/checkout/checkoutCopy";
import type { CheckoutReadDTO, CheckoutRequestDTO } from "@/lib/checkout/checkoutTypes";
import type { PublicSettingsRead } from "@/lib/settings/publicSettingsModel";
import { CheckoutView } from "./CheckoutView";

// /checkout end to end at the component level: the real hooks, a real
// QueryClient, and the network mocked at the API-module boundary only.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
vi.mock("@/lib/checkout/paymentRedirect", () => ({
  followPaymentRedirect: vi.fn(),
}));
import { useAuth } from "@/lib/auth/AuthProvider";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
const mockedUseAuth = vi.mocked(useAuth);
const mockedRedirect = vi.mocked(followPaymentRedirect);

function signIn(emailVerified = true) {
  mockedUseAuth.mockReturnValue({
    user: {
      id: "u-1",
      email: "a@b.c",
      role: "customer",
      emailVerified,
      emailVerifiedAt: null,
      createdAt: "",
    },
    isAuthenticated: true,
    isLoading: false,
    isError: false,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>);
}

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

function line(overrides: Partial<CartLineReadDTO> = {}): CartLineReadDTO {
  return {
    product_id: "p-dragon",
    product_type: "physical",
    name: "Articulated Dragon",
    slug: "dragon",
    cover_image: null,
    quantity: 2,
    snapshot_price: usd(1800),
    current_price: usd(1800),
    price_changed: false,
    max_quantity: 3,
    over_cap: false,
    purchasable: true,
    unpurchasable_reason: null,
    ...overrides,
  };
}
const STL = line({
  product_id: "p-stl",
  product_type: "stl",
  name: "Dragon STL",
  quantity: 1,
  max_quantity: null,
  snapshot_price: usd(900),
  current_price: usd(900),
});

function cartOf(items: CartLineReadDTO[]): CartReadDTO {
  return {
    id: items.length ? "cart-1" : null,
    items,
    contains_physical: items.some((i) => i.product_type === "physical"),
    contains_digital: items.some((i) => i.product_type === "stl"),
    updated_at: null,
  };
}

const ADDRESS: AddressReadDTO = {
  id: "a-home",
  label: "Home",
  recipient_name: "Ada",
  phone: "+96170123456",
  governorate: "beqaa",
  city: "Zahle",
  area: null,
  street: "Main St",
  landmark_notes: "Blue door",
  is_default: true,
  created_at: "",
  updated_at: "",
};

const SETTINGS: PublicSettingsRead = {
  accepting_orders: true,
  cash_payment_enabled: true,
  cash_max_order_total: usd(10000),
  pickup_address: "Bekaa3D workshop, Zahle",
  pickup_hours: "Mon-Fri 10:00-18:00",
  whatsapp_number: null,
};

function cashRead(overrides: Partial<CheckoutReadDTO["order"]> = {}): CheckoutReadDTO {
  return {
    order: {
      id: "o-1",
      order_number: "B3D-2026-000123",
      source: "cart",
      status: "in_progress",
      payment_method: "cash",
      fulfillment_method: "delivery",
      subtotal: usd(3600),
      tax: usd(0),
      total: usd(3600),
      placed_at: "2026-11-11T10:00:00Z",
      estimated_dispatch_at: "2026-11-14T10:00:00Z",
      delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
      delivery_address: {
        recipient_name: "Ada",
        governorate: "beqaa",
        city: "Zahle",
        area: null,
        street: "Main St",
        landmark_notes: "Blue door",
      },
      payment_due: true,
      amount_due: usd(3600),
      lines: [
        {
          id: "l-1",
          product_id: "p-dragon",
          product_type: "physical",
          name: "Articulated Dragon",
          unit_price: usd(1800),
          quantity: 2,
          line_total: usd(3600),
          fulfillment_status: "pending",
        },
      ],
      ...overrides,
    },
    payment: null,
    dropped_lines: [],
  };
}

function onlineRead(
  dropped: string[] = [],
  redirect: string | null = "http://localhost:3000/checkout/return?order=B3D-2026-000124"
): CheckoutReadDTO {
  const base = cashRead({
    order_number: "B3D-2026-000124",
    status: "pending_payment",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
  });
  return {
    ...base,
    payment: {
      id: "pay-1",
      status: "pending",
      provider: "mock",
      redirect_url: redirect,
    },
    dropped_lines: dropped.map((product_id) => ({
      product_id,
      reason: "already_owned" as const,
    })),
  };
}

function problem(
  status: number,
  code: string,
  extensions: Record<string, unknown> = {},
  extra: Partial<ApiError> = {}
): ApiError {
  return {
    kind: "http",
    status,
    code,
    title: "RAW TITLE",
    detail: "RAW DETAIL",
    message: "x",
    raw: {
      status,
      code,
      title: "RAW TITLE",
      detail: "RAW DETAIL",
      errors: [],
      ...extensions,
    },
    ...extra,
  };
}

let cart: CartReadDTO;
let settings: PublicSettingsRead;
let getCartSpy: MockInstance<typeof cartApi.getCart>;
let placeSpy: MockInstance<typeof checkoutApi.placeOrder>;

beforeEach(() => {
  signIn();
  cart = cartOf([line()]);
  settings = { ...SETTINGS };
  getCartSpy = vi.spyOn(cartApi, "getCart").mockImplementation(async () => cart);
  vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({
    items: [ADDRESS],
  });
  vi.spyOn(apiClient, "get").mockImplementation(async (path: string) => {
    if (path === "/api/v1/settings/public") return settings;
    throw new Error(`unexpected GET ${path}`);
  });
  placeSpy = vi.spyOn(checkoutApi, "placeOrder");
});

afterEach(() => {
  vi.restoreAllMocks();
  mockedRedirect.mockReset();
});

function renderView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<CheckoutView />, { wrapper });
}

const user = () => userEvent.setup();

async function chooseDeliveryOnline(u: ReturnType<typeof userEvent.setup>) {
  await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
  await u.click(screen.getByRole("radio", { name: /Pay online/ }));
  await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
}

function sentBodies(): CheckoutRequestDTO[] {
  return placeSpy.mock.calls.map((call) => call[0]);
}
function sentKeys(): string[] {
  return placeSpy.mock.calls.map((call) => call[1]);
}

describe("CheckoutView guards", () => {
  it("an unverified account gets truthful guidance and no form", async () => {
    signIn(false);
    renderView();
    expect(await screen.findByText(/Verify your email address before placing an order/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resend the verification email" })).toHaveAttribute(
      "href",
      "/verify-email/resend"
    );
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
  });

  it("an empty cart cannot proceed", async () => {
    cart = cartOf([]);
    renderView();
    expect(await screen.findByText("Your cart is empty, so there's nothing to check out.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
  });

  it("unpurchasable / over-cap lines block checkout and are named, with a link back to the cart", async () => {
    cart = cartOf([
      line(),
      line({
        product_id: "p-lamp",
        name: "Moon Lamp",
        purchasable: false,
        unpurchasable_reason: "whatsapp_only",
      }),
    ]);
    renderView();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Moon Lamp can only be ordered through WhatsApp.");
    expect(within(alert).getByRole("link", { name: "Review your cart" })).toHaveAttribute("href", "/cart");
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
  });

  it("paused shop: banner, no form", async () => {
    settings = { ...SETTINGS, accepting_orders: false };
    renderView();
    expect(await screen.findByText(/isn't accepting orders right now/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
  });

  it("shows no total before checkout, only unit prices", async () => {
    renderView();
    await screen.findByRole("button", { name: "Place order" });
    expect(screen.queryByText(/^Total$/)).not.toBeInTheDocument();
    expect(screen.queryByText("$36.00")).not.toBeInTheDocument();
    expect(screen.getByText("$18.00")).toBeInTheDocument();
  });
});

describe("CheckoutView submission", () => {
  it("validates locally first and sends nothing while choices are missing", async () => {
    const u = user();
    renderView();
    await u.click(await screen.findByRole("button", { name: "Place order" }));
    expect(placeSpy).not.toHaveBeenCalled();
    expect(screen.getByText("Please check the highlighted details before placing your order.")).toBeInTheDocument();
    expect(screen.getByText("Choose delivery or pickup.")).toBeInTheDocument();
    expect(screen.getByText("Choose how you'd like to pay.")).toBeInTheDocument();
  });

  it("delivery + saved address + cash: exact body, response-backed confirmation, cart refetched", async () => {
    placeSpy.mockResolvedValue(cashRead());
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
    // The default address is preselected from the customer's own address book.
    expect(await screen.findByRole("radio", { name: /Home/ })).toBeChecked();
    await u.click(screen.getByRole("radio", { name: /Pay in cash/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms }));
    const cartReads = getCartSpy.mock.calls.length;
    await u.click(screen.getByRole("button", { name: "Place order" }));

    expect(await screen.findByRole("heading", { name: "Order placed" })).toBeInTheDocument();
    expect(sentBodies()).toEqual([
      {
        payment_method: "cash",
        fulfillment_method: "delivery",
        address_id: "a-home",
        accept_terms: true,
        accept_cash_terms: true,
      },
    ]);
    expect(sentKeys()[0]).toMatch(/^[A-Za-z0-9._:-]{8,255}$/);
    expect(screen.getByText("B3D-2026-000123")).toBeInTheDocument();
    expect(screen.getByText(/Payment due in cash to the courier on delivery/)).toBeInTheDocument();
    expect(screen.getByText(/This order hasn't been paid yet\./)).toBeInTheDocument();
    expect(screen.queryByText(/payment (was )?successful/i)).not.toBeInTheDocument();
    expect(mockedRedirect).not.toHaveBeenCalled();
    // Phase 5E: the new order can be opened on its real order page.
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute("href", "/account/orders/o-1");
    await waitFor(() => expect(getCartSpy.mock.calls.length).toBeGreaterThan(cartReads));
  });

  it("pickup + online: contact phone, no address, and the opaque redirect is followed as given", async () => {
    placeSpy.mockResolvedValue(onlineRead());
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Pickup/ }));
    expect(screen.getByText("Bekaa3D workshop, Zahle")).toBeInTheDocument();
    await u.type(screen.getByLabelText("Contact phone"), " 70 123 456 ");
    await u.click(screen.getByRole("radio", { name: /Pay online/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("button", { name: "Place order" }));

    await waitFor(() =>
      expect(mockedRedirect).toHaveBeenCalledWith("http://localhost:3000/checkout/return?order=B3D-2026-000124")
    );
    expect(sentBodies()).toEqual([
      {
        payment_method: "online",
        fulfillment_method: "pickup",
        contact_phone: "70 123 456",
        accept_terms: true,
      },
    ]);
    expect(screen.getByRole("status")).toHaveTextContent("awaiting payment");
  });

  it("STL only: no fulfillment, the final-sale consent, online only (cash disabled with the reason)", async () => {
    cart = cartOf([STL]);
    placeSpy.mockResolvedValue(onlineRead());
    const u = user();
    renderView();
    expect(await screen.findByText(/Your order only has STL files/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /^Delivery/ })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Pay in cash/ })).toBeDisabled();
    await u.click(screen.getByRole("radio", { name: /Pay online/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.digitalFinalSale }));
    await u.click(screen.getByRole("button", { name: "Place order" }));
    await waitFor(() => expect(placeSpy).toHaveBeenCalledTimes(1));
    expect(sentBodies()[0]).toEqual({
      payment_method: "online",
      accept_terms: true,
      accept_digital_final_sale: true,
    });
  });

  it("a double click places one request only", async () => {
    let resolve!: (value: CheckoutReadDTO) => void;
    placeSpy.mockImplementation(() => new Promise((r) => (resolve = r)));
    const u = user();
    renderView();
    await chooseDeliveryOnline(u);
    const button = screen.getByRole("button", { name: "Place order" });
    await u.dblClick(button);
    await u.click(button);
    expect(placeSpy).toHaveBeenCalledTimes(1);
    resolve(onlineRead());
    await waitFor(() => expect(mockedRedirect).toHaveBeenCalledTimes(1));
  });

  it("CART_PRICE_CHANGED: names the lines, blocks until explicitly accepted, then resubmits with accepted_price_changes and a NEW key", async () => {
    placeSpy
      .mockRejectedValueOnce(
        problem(409, "CART_PRICE_CHANGED", {
          price_changes: [
            {
              product_id: "p-dragon",
              old_amount_cents: 1800,
              new_amount_cents: 2100,
              currency: "USD",
            },
          ],
        })
      )
      .mockResolvedValueOnce(onlineRead());
    const u = user();
    renderView();
    await chooseDeliveryOnline(u);
    await u.click(screen.getByRole("button", { name: "Place order" }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Articulated Dragon");
    expect(banner).toHaveTextContent("$21.00");
    expect(screen.getByRole("button", { name: "Place order" })).toBeDisabled();
    expect(placeSpy).toHaveBeenCalledTimes(1);

    await u.click(screen.getByRole("button", { name: "Accept new prices" }));
    expect(placeSpy).toHaveBeenCalledTimes(1); // accepting never submits by itself
    await u.click(screen.getByRole("button", { name: "Place order" }));

    await waitFor(() => expect(placeSpy).toHaveBeenCalledTimes(2));
    expect(sentBodies()[1]!.accepted_price_changes).toEqual([
      { product_id: "p-dragon", amount_cents: 2100, currency: "USD" },
    ]);
    expect(sentKeys()[1]).not.toBe(sentKeys()[0]);
    await waitFor(() => expect(mockedRedirect).toHaveBeenCalled());
  });

  it("refused lines: named with reasons, cart refetched, form and cart kept, no success", async () => {
    placeSpy.mockRejectedValue(
      problem(422, "PRODUCT_NOT_PURCHASABLE", {
        lines: [{ product_id: "p-dragon", reason: "unavailable" }],
      })
    );
    const u = user();
    renderView();
    await chooseDeliveryOnline(u);
    const reads = getCartSpy.mock.calls.length;
    await u.click(screen.getByRole("button", { name: "Place order" }));
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("Some items in your cart can't be ordered right now.");
    expect(notice).toHaveTextContent("Articulated Dragon is currently unavailable.");
    await waitFor(() => expect(getCartSpy.mock.calls.length).toBeGreaterThan(reads));
    expect(screen.queryByRole("heading", { name: /Order placed|awaiting payment/ })).not.toBeInTheDocument();
    expect(screen.queryByText("RAW DETAIL")).not.toBeInTheDocument();
  });

  it("dropped_lines on an online order: says they weren't charged and waits for an explicit Continue to payment", async () => {
    cart = cartOf([line(), STL]);
    placeSpy.mockResolvedValue(onlineRead(["p-stl"]));
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
    await u.click(screen.getByRole("radio", { name: /Pay online/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.digitalFinalSale }));
    await u.click(screen.getByRole("button", { name: "Place order" }));

    expect(
      await screen.findByRole("heading", {
        name: "Your order is awaiting payment",
      })
    ).toBeInTheDocument();
    expect(screen.getByText(/not included in your order because you already own them/)).toBeInTheDocument();
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
    expect(mockedRedirect).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute("href", "/account/orders/o-1");
    await u.click(screen.getByRole("button", { name: "Continue to payment" }));
    expect(mockedRedirect).toHaveBeenCalledWith("http://localhost:3000/checkout/return?order=B3D-2026-000124");
  });

  it("an unknown outcome locks the form and retries with the SAME key and body", async () => {
    placeSpy.mockRejectedValueOnce({ kind: "timeout", message: "x", raw: undefined }).mockResolvedValueOnce(cashRead());
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
    await u.click(screen.getByRole("radio", { name: /Pay in cash/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms }));
    const reads = getCartSpy.mock.calls.length;
    await u.click(screen.getByRole("button", { name: "Place order" }));

    expect(await screen.findByText(CHECKOUT_MESSAGES.uncertain)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
    expect(getCartSpy.mock.calls.length).toBe(reads);
    await u.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Order placed" })).toBeInTheDocument();
    expect(sentKeys()[1]).toBe(sentKeys()[0]);
    expect(sentBodies()[1]).toEqual(sentBodies()[0]);
  });

  it("a definitive refusal keeps the cart and the form (CASH_NOT_AVAILABLE)", async () => {
    placeSpy.mockRejectedValue(problem(422, "CASH_NOT_AVAILABLE"));
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
    await u.click(screen.getByRole("radio", { name: /Pay in cash/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms }));
    const reads = getCartSpy.mock.calls.length;
    await u.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByText(CHECKOUT_MESSAGES.cashNotAvailable)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Place order" })).toBeEnabled();
    expect(screen.getByText("Articulated Dragon")).toBeInTheDocument();
    expect(getCartSpy.mock.calls.length).toBe(reads);
  });

  it("cash above the public limit: CASH_PAYMENT_LIMIT_REACHED names the limit", async () => {
    placeSpy.mockRejectedValue(problem(422, "CASH_PAYMENT_LIMIT_REACHED", { reason: "order_total" }));
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Delivery/ }));
    await u.click(screen.getByRole("radio", { name: /Pay in cash/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.cashTerms }));
    await u.click(screen.getByRole("button", { name: "Place order" }));
    expect(
      await screen.findByText("This order is above the $100.00 limit for cash payment. Please pay online.")
    ).toBeInTheDocument();
  });

  it("a server VALIDATION_ERROR on contact_phone becomes frontend copy on the field", async () => {
    placeSpy.mockRejectedValue(
      problem(
        422,
        "VALIDATION_ERROR",
        {},
        {
          errors: [
            {
              loc: ["body", "contact_phone"],
              msg: "RAW MSG",
              type: "value_error",
            },
          ],
        }
      )
    );
    const u = user();
    renderView();
    await u.click(await screen.findByRole("radio", { name: /^Pickup/ }));
    await u.type(screen.getByLabelText("Contact phone"), "123");
    await u.click(screen.getByRole("radio", { name: /Pay online/ }));
    await u.click(screen.getByRole("checkbox", { name: CONSENT_COPY.terms }));
    await u.click(screen.getByRole("button", { name: "Place order" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Contact phone")).toHaveAccessibleDescription(
        /Enter a valid Lebanese phone number\./
      )
    );
    expect(screen.queryByText("RAW MSG")).not.toBeInTheDocument();
  });

  it("502 PAYMENT_PROVIDER_UNAVAILABLE: the order exists unpaid, never shown as success; the cart is refetched", async () => {
    placeSpy.mockRejectedValue(
      problem(502, "PAYMENT_PROVIDER_UNAVAILABLE", {
        order_id: "o-9",
        order_number: "B3D-2026-000999",
      })
    );
    const u = user();
    renderView();
    await chooseDeliveryOnline(u);
    const reads = getCartSpy.mock.calls.length;
    await u.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByRole("heading", { name: "Payment not started" })).toBeInTheDocument();
    expect(screen.getByText("B3D-2026-000999")).toBeInTheDocument();
    expect(screen.getByText(/nothing has been charged/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute("href", "/account/orders/o-9");
    await waitFor(() => expect(getCartSpy.mock.calls.length).toBeGreaterThan(reads));
  });

  it("CSRF and session expiry use safe copy; session expiry offers a login that returns to /checkout", async () => {
    placeSpy.mockRejectedValueOnce(problem(403, "CSRF_INVALID")).mockRejectedValueOnce(problem(401, "AUTH_REQUIRED"));
    const u = user();
    renderView();
    await chooseDeliveryOnline(u);
    await u.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByText(CHECKOUT_MESSAGES.csrf)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByRole("link", { name: "Log in again" })).toHaveAttribute(
      "href",
      "/login?returnTo=%2Fcheckout"
    );
  });
});
