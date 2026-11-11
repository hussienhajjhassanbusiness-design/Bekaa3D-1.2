import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { offersAdminApi } from "@/lib/admin/offers/offersAdminApi";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import type { CheckoutReadDTO } from "@/lib/checkout/checkoutTypes";
import { adminOfferDetail, OFFER_ID, OFFER_PRODUCT_ID, offerDetail } from "@/lib/offers/offerFixtures";
import { offersApi } from "@/lib/offers/offersApi";
import { AdminOfferView } from "@/components/admin/offers/AdminOfferView";
import { CustomerOfferView } from "./CustomerOfferView";
import { MakeOfferPanel } from "./MakeOfferPanel";

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
vi.mock("@/lib/checkout/paymentRedirect", () => ({ followPaymentRedirect: vi.fn() }));
import { useAuth } from "@/lib/auth/AuthProvider";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
const mockedUseAuth = vi.mocked(useAuth);
const mockedRedirect = vi.mocked(followPaymentRedirect);

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

function renderWithQuery(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  return client;
}

function http(status: number, code: string, extra: Record<string, unknown> = {}): ApiError {
  return { kind: "http", status, code, title: "RAW TITLE", detail: "RAW DETAIL", message: "RAW", raw: { code, ...extra } };
}

const CHECKOUT: CheckoutReadDTO = {
  order: {
    id: "00000000-0000-4000-8000-0000000000d1",
    order_number: "B3D-OFFER-1",
    source: "offer",
    status: "pending_payment",
    payment_method: "online",
    fulfillment_method: null,
    subtotal: { amount_cents: 1500, currency: "USD" },
    tax: { amount_cents: 0, currency: "USD" },
    total: { amount_cents: 1500, currency: "USD" },
    placed_at: "2026-11-12T11:00:00Z",
    estimated_dispatch_at: null,
    delivery_fee_note: null,
    delivery_address: null,
    payment_due: false,
    amount_due: null,
    lines: [],
  },
  payment: { id: "p-1", status: "pending", provider: "mock", redirect_url: "http://localhost:8000/mock-pay/p-1" },
  dropped_lines: [],
} as unknown as CheckoutReadDTO;

afterEach(() => {
  vi.restoreAllMocks();
  mockedRedirect.mockReset();
});

const PANEL = { productId: OFFER_PRODUCT_ID, productName: "Dragon STL", canOffer: true, returnToPath: "/shop/dragon-stl" };

describe("MakeOfferPanel", () => {
  it("renders nothing without the server's can_offer capability, or while auth loads", () => {
    viewer("verified");
    const { container } = render(<MakeOfferPanel {...PANEL} canOffer={false} />);
    expect(container).toBeEmptyDOMElement();
    viewer("loading");
    const second = render(<MakeOfferPanel {...PANEL} />);
    expect(second.container).toBeEmptyDOMElement();
  });

  it("sends an anonymous visitor to sign in with a safe returnTo, and an unverified one to verification", () => {
    viewer("anonymous");
    const { unmount } = render(<MakeOfferPanel {...PANEL} />);
    expect(screen.getByRole("link", { name: "Make an offer" })).toHaveAttribute("href", buildLoginRedirectPath("/shop/dragon-stl"));
    unmount();
    viewer("unverified");
    render(<MakeOfferPanel {...PANEL} />);
    expect(screen.getByRole("link", { name: "Verify your email" })).toHaveAttribute("href", "/verify-email/resend");
  });

  it("links a live offer instead of offering a doomed form", async () => {
    viewer("verified");
    const list = vi.spyOn(offersApi, "listMyOffers").mockResolvedValue({ items: [offerDetail({ status: "awaiting_customer" })], next_cursor: null });
    renderWithQuery(<MakeOfferPanel {...PANEL} />);
    expect(await screen.findByRole("link", { name: "View your offer" })).toHaveAttribute("href", `/account/offers/${OFFER_ID}`);
    expect(screen.queryByRole("button", { name: "Make an offer" })).toBeNull();
    expect(list).toHaveBeenCalledWith({ productId: OFFER_PRODUCT_ID, limit: 5 });
  });

  it("validates locally, shows the server's minimum, then sends the offer", async () => {
    viewer("verified");
    vi.spyOn(offersApi, "listMyOffers").mockResolvedValue({ items: [offerDetail({ status: "expired" })], next_cursor: null });
    const create = vi
      .spyOn(offersApi, "createOffer")
      .mockRejectedValueOnce(http(422, "OFFER_BELOW_MINIMUM", { minimum: { amount_cents: 1050, currency: "USD" } }))
      .mockResolvedValueOnce(offerDetail());
    renderWithQuery(<MakeOfferPanel {...PANEL} />);
    const user = userEvent.setup();
    const toggle = await screen.findByRole("button", { name: "Make an offer" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Send offer" }));
    expect(screen.getByText("Enter the amount you'd like to offer.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Your offer (USD)"), "9");
    await user.type(screen.getByLabelText("Message (optional)"), "Please?");
    await user.click(screen.getByRole("button", { name: "Send offer" }));
    expect(await screen.findByText("The lowest offer we can accept for this product is $10.50.")).toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).toBeNull();

    await user.clear(screen.getByLabelText("Your offer (USD)"));
    await user.type(screen.getByLabelText("Your offer (USD)"), "12.50");
    await user.click(screen.getByRole("button", { name: "Send offer" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your offer was sent.");
    expect(create).toHaveBeenLastCalledWith({ productId: OFFER_PRODUCT_ID, amountCents: 1250, message: "Please?" });
  });

  it("links the existing offer on OFFER_ALREADY_ACTIVE", async () => {
    viewer("verified");
    vi.spyOn(offersApi, "listMyOffers").mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(offersApi, "createOffer").mockRejectedValue(http(409, "OFFER_ALREADY_ACTIVE"));
    renderWithQuery(<MakeOfferPanel {...PANEL} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Make an offer" }));
    await user.type(screen.getByLabelText("Your offer (USD)"), "12");
    await user.click(screen.getByRole("button", { name: "Send offer" }));
    expect(await screen.findByText("You already have an offer in progress on this product.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View your offers" })).toHaveAttribute("href", "/account/offers");
  });
});

describe("CustomerOfferView", () => {
  it("shows the same not-found state for a malformed id and a 404", async () => {
    viewer("verified");
    const get = vi.spyOn(offersApi, "getMyOffer").mockRejectedValue(http(404, "NOT_FOUND"));
    renderWithQuery(<CustomerOfferView offerId="not-a-uuid" />);
    expect(screen.getByRole("heading", { name: "Offer not found" })).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
    document.body.innerHTML = "";
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    expect(await screen.findByRole("heading", { name: "Offer not found" })).toBeInTheDocument();
  });

  it("renders the history as plain text and only the server's allowed moves", async () => {
    viewer("verified");
    vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(offerDetail());
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    expect(await screen.findByRole("heading", { name: "Offer on Dragon STL" })).toBeInTheDocument();
    expect(screen.getByText("<b>Would you take $15?</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
    expect(screen.getByText("Waiting for our reply")).toBeInTheDocument();
    const actions = screen.getByRole("region", { name: "Your reply" });
    expect(within(actions).getAllByRole("button").map((b) => b.textContent)).toEqual(["Withdraw offer"]);
    expect(screen.queryByRole("region", { name: "Check out at the agreed price" })).toBeNull();
  });

  it("accepts with the amount as last seen and refreshes the offer when it moved on", async () => {
    viewer("verified");
    const countered = offerDetail({
      status: "awaiting_customer",
      turn: "customer",
      current_amount: { amount_cents: 1800, currency: "USD" },
      allowed_actions: ["counter", "accept", "withdraw"],
    });
    const get = vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(countered);
    const accept = vi.spyOn(offersApi, "acceptOffer").mockRejectedValueOnce(http(409, "OFFER_AMOUNT_CHANGED", { current_amount: { amount_cents: 1900, currency: "USD" } }));
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Accept this amount" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("$18.00");
    await user.click(within(dialog).getByRole("button", { name: "Accept" }));
    expect(accept).toHaveBeenCalledWith(OFFER_ID, 1800);
    expect(await screen.findByText(/The amount on the table is now \$19\.00/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("sends a counter-offer with its message and stores the server's answer", async () => {
    viewer("verified");
    const mine = offerDetail({ status: "awaiting_customer", turn: "customer", allowed_actions: ["counter", "accept", "withdraw"] });
    vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(mine);
    const counter = vi.spyOn(offersApi, "counterOffer").mockResolvedValue(offerDetail({ status: "awaiting_admin", allowed_actions: ["withdraw"] }));
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Counter-offer" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Send counter-offer" }));
    expect(within(dialog).getByText("Enter an amount of at least $0.01.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Your counter-offer (USD)"), "16");
    await user.type(within(dialog).getByLabelText("Message (optional)"), "Meet me halfway");
    await user.click(within(dialog).getByRole("button", { name: "Send counter-offer" }));
    expect(counter).toHaveBeenCalledWith(OFFER_ID, 1600, "Meet me halfway");
    expect(await screen.findByRole("status")).toHaveTextContent("Your counter-offer was sent.");
    expect(screen.getByText("Waiting for our reply")).toBeInTheDocument();
  });

  it("checks out an accepted offer with consents and one idempotency key, then follows the server's redirect", async () => {
    viewer("verified");
    vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(
      offerDetail({
        status: "accepted",
        turn: null,
        agreed_amount: { amount_cents: 1500, currency: "USD" },
        responds_by: null,
        checkout_expires_at: "2026-11-13T10:00:00Z",
        allowed_actions: [],
      })
    );
    const checkout = vi
      .spyOn(offersApi, "checkoutOffer")
      .mockRejectedValueOnce({ kind: "timeout", message: "x", raw: undefined })
      .mockResolvedValueOnce(CHECKOUT);
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    const user = userEvent.setup();
    const panel = await screen.findByRole("region", { name: "Check out at the agreed price" });
    expect(panel).toHaveTextContent("$15.00");
    await user.click(within(panel).getByRole("button", { name: "Check out and pay" }));
    expect(within(panel).getByText("Please accept the terms of sale to check out.")).toBeInTheDocument();
    expect(checkout).not.toHaveBeenCalled();
    for (const box of within(panel).getAllByRole("checkbox")) await user.click(box);
    await user.click(within(panel).getByRole("button", { name: "Check out and pay" }));
    expect(await within(panel).findByRole("heading", { name: "Checking your order" })).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mockedRedirect).toHaveBeenCalledWith("http://localhost:8000/mock-pay/p-1"));
    expect(checkout).toHaveBeenCalledTimes(2);
    expect(checkout.mock.calls[0]?.[1]).toBe(checkout.mock.calls[1]?.[1]);
  });
});

describe("AdminOfferView", () => {
  it("renders the server's admin moves and rejects through a destructive confirmation", async () => {
    vi.spyOn(offersAdminApi, "getOffer").mockResolvedValue(adminOfferDetail());
    const reject = vi.spyOn(offersAdminApi, "rejectOffer").mockResolvedValue(adminOfferDetail({ status: "rejected", turn: null, allowed_actions: [] }));
    renderWithQuery(<AdminOfferView offerId={OFFER_ID} />);
    expect(await screen.findByRole("heading", { name: "Offer on Dragon STL" })).toBeInTheDocument();
    expect(screen.getByText(/rana@example\.com/)).toBeInTheDocument();
    const actions = screen.getByRole("region", { name: "Your reply" });
    expect(within(actions).getAllByRole("button").map((b) => b.textContent)).toEqual(["Accept offer", "Counter-offer", "Reject offer"]);
    const user = userEvent.setup();
    await user.click(within(actions).getByRole("button", { name: "Reject offer" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reject offer" }));
    expect(reject).toHaveBeenCalledWith(OFFER_ID, "");
    expect(await screen.findByRole("status")).toHaveTextContent("Offer rejected.");
    expect(screen.queryByRole("region", { name: "Your reply" })).toBeNull();
  });

  it("keeps the dialog open with a CSRF refusal and never shows server text", async () => {
    vi.spyOn(offersAdminApi, "getOffer").mockResolvedValue(adminOfferDetail());
    vi.spyOn(offersAdminApi, "acceptOffer").mockRejectedValue(http(403, "CSRF_INVALID"));
    renderWithQuery(<AdminOfferView offerId={OFFER_ID} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Accept offer" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Accept" }));
    expect(await within(dialog).findByText(/Unable to verify your session/)).toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).toBeNull();
  });

  it("shows not-found for a 404 (a customer probing the admin route)", async () => {
    vi.spyOn(offersAdminApi, "getOffer").mockRejectedValue(http(404, "NOT_FOUND"));
    renderWithQuery(<AdminOfferView offerId={OFFER_ID} />);
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your reply" })).toBeNull();
  });
});
