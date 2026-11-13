import type { ReactNode } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { OFFER_ID, offerDetail } from "@/lib/offers/offerFixtures";
import { offersApi } from "@/lib/offers/offersApi";
import type { OfferStatus, OfferSummaryReadDTO } from "@/lib/offers/offerTypes";
import { CustomerOfferView } from "./CustomerOfferView";
import { OfferFacts } from "./OfferFacts";
import { OfferHistory } from "./OfferHistory";
import { OfferList, type OfferListProps } from "./OfferList";

// Redesign Batch 7 — presentation of the customer offer list and detail.
// Behaviour (moves, checkout, refusals) stays covered by offers.test.tsx;
// these pin the structure the redesign relies on.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
vi.mock("@/lib/checkout/paymentRedirect", () => ({ followPaymentRedirect: vi.fn() }));

function http(status: number, code: string): ApiError {
  return { kind: "http", status, code, title: "RAW TITLE", detail: "RAW DETAIL", message: "RAW", raw: { code } };
}

function summary(overrides: Partial<OfferSummaryReadDTO> = {}): OfferSummaryReadDTO {
  const detail = offerDetail();
  return {
    id: detail.id,
    product: detail.product,
    status: detail.status,
    turn: detail.turn,
    current_amount: detail.current_amount,
    agreed_amount: detail.agreed_amount,
    responds_by: detail.responds_by,
    checkout_expires_at: detail.checkout_expires_at,
    created_at: detail.created_at,
    ...overrides,
  };
}

function renderList(props: Partial<OfferListProps> = {}) {
  const onRetry = vi.fn();
  const onLoadMore = vi.fn();
  render(
    <OfferList
      offers={[]}
      isLoading={false}
      error={null}
      onRetry={onRetry}
      hasNextPage={false}
      isFetchingNextPage={false}
      onLoadMore={onLoadMore}
      loadMoreFailed={false}
      {...props}
    />
  );
  return { onRetry, onLoadMore };
}

function renderWithQuery(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("OfferList (Batch 7)", () => {
  it("announces loading", () => {
    renderList({ isLoading: true });
    expect(screen.getByRole("status")).toHaveTextContent("Loading your offers…");
  });

  it("shows the empty state with a shop link", () => {
    renderList();
    expect(screen.getByText(/haven't made any offers yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");
  });

  it("shows safe copy with a retry, and a sign-in link for an expired session", async () => {
    const { onRetry } = renderList({ error: http(500, "INTERNAL_ERROR") });
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load your offers. Please try again.");
    expect(screen.queryByText(/RAW/)).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("links an expired session to sign-in with returnTo", () => {
    renderList({ error: http(401, "AUTHENTICATION_REQUIRED") });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      buildLoginRedirectPath("/account/offers")
    );
  });

  it("renders one row per offer with a single link, the status as text, the amount and the deadline", () => {
    renderList({
      offers: [
        summary(),
        summary({
          id: "00000000-0000-4000-8000-0000000000a2",
          status: "accepted",
          agreed_amount: { amount_cents: 1800, currency: "USD" },
          checkout_expires_at: "2026-11-15T10:00:00Z",
          responds_by: null,
        }),
      ],
    });
    const [open, accepted] = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement];
    expect(within(open).getAllByRole("link")).toHaveLength(1);
    expect(within(open).getByRole("link", { name: "Offer on Dragon STL" })).toHaveAttribute(
      "href",
      `/account/offers/${OFFER_ID}`
    );
    expect(open).toHaveTextContent("Waiting for our reply");
    expect(open).toHaveTextContent(/Amount on the table\$15\.00/);
    expect(open).toHaveTextContent(/Reply by/);
    expect(accepted).toHaveTextContent("Accepted: ready to check out");
    expect(accepted).toHaveTextContent(/Agreed price\$18\.00/);
    expect(accepted).toHaveTextContent(/Check out by/);
  });

  it("keeps every server state distinct and degrades an unknown one", () => {
    const states: OfferStatus[] = [
      "awaiting_customer",
      "rejected",
      "withdrawn",
      "expired",
      "checkout_expired",
      "paid",
      "auto_closed",
    ];
    renderList({
      offers: [
        ...states.map((status, index) => summary({ id: `id-${index}`, status, responds_by: null })),
        summary({ id: "id-x", status: "brand_new" as OfferStatus }),
      ],
    });
    const rows = screen.getAllByRole("listitem").map((row) => row.textContent ?? "");
    for (const label of [
      "Your reply needed",
      "Declined",
      "Withdrawn",
      "Expired",
      "Checkout window ended",
      "Paid",
      "Closed: STL bought another way",
      "Status unavailable",
    ]) {
      expect(rows.some((text) => text.includes(label))).toBe(true);
    }
  });

  it("loads more and states a failed page without hiding loaded rows", async () => {
    const { onLoadMore } = renderList({ offers: [summary()], hasNextPage: true, loadMoreFailed: true });
    expect(screen.getByRole("listitem")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load more offers.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Load more offers" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});

describe("CustomerOfferView structure (Batch 7)", () => {
  it("puts the status in the h1's parent, names the sections and keeps the history ordered", async () => {
    vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(
      offerDetail({
        status: "awaiting_customer",
        allowed_actions: ["accept", "counter", "withdraw"],
        rounds: [
          {
            sequence: 2,
            actor: "admin",
            action: "countered",
            amount: { amount_cents: 1800, currency: "USD" },
            message: "We can do $18.",
            created_at: "2026-11-12T11:00:00Z",
          },
          {
            sequence: 1,
            actor: "customer",
            action: "submitted",
            amount: { amount_cents: 1500, currency: "USD" },
            message: null,
            created_at: "2026-11-12T10:00:00Z",
          },
        ],
      })
    );
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    const h1 = await screen.findByRole("heading", { level: 1, name: "Offer on Dragon STL" });
    expect(h1.parentElement).toHaveTextContent("Your reply needed");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "View product" })).toHaveAttribute("href", "/shop/dragon-stl");
    expect(screen.getByRole("link", { name: "Your offers" })).toHaveAttribute("href", "/account/offers");
    expect(within(screen.getByRole("region", { name: "Offer details" })).getByText("First offer")).toBeInTheDocument();
    // Buttons are exactly the server's allowed moves, one primary first.
    const reply = screen.getByRole("region", { name: "Your reply" });
    expect(
      within(reply)
        .getAllByRole("button")
        .map((b) => b.textContent)
    ).toEqual(["Accept this amount", "Counter-offer", "Withdraw offer"]);
    const history = screen.getByRole("region", { name: "History" });
    const rounds = within(history)
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "");
    expect(rounds[0]).toContain("You offered $15.00");
    expect(rounds[1]).toContain("Bekaa3D countered with $18.00");
    expect(rounds[1]).toContain("We can do $18.");
  });

  it("offers no reply region when the server lists no moves", async () => {
    vi.spyOn(offersApi, "getMyOffer").mockResolvedValue(
      offerDetail({ status: "expired", allowed_actions: [], responds_by: null })
    );
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    expect(await screen.findByText("Expired", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your reply" })).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps one h1 while loading and in the not-found state", async () => {
    vi.spyOn(offersApi, "getMyOffer").mockRejectedValue(http(404, "NOT_FOUND"));
    renderWithQuery(<CustomerOfferView offerId={OFFER_ID} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading this offer…");
    expect(await screen.findByRole("heading", { level: 1, name: "Offer not found" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "View your offers" })).toHaveAttribute("href", "/account/offers");
  });
});

describe("shared offer facts / history appearance", () => {
  it("defaults to the original rendering (the admin page is not redesigned in Batch 7)", () => {
    const { container } = render(
      <>
        <OfferFacts offer={offerDetail()} />
        <OfferHistory rounds={offerDetail().rounds} perspective="admin" />
      </>
    );
    expect(container.querySelector("dt")).toHaveClass("text-text-secondary");
    expect(container.querySelector("section")).not.toHaveClass("rounded-card");
  });

  it("account appearance keeps the same facts and an ordered history list", () => {
    render(
      <>
        <OfferFacts
          offer={offerDetail({ agreed_amount: { amount_cents: 1700, currency: "USD" } })}
          appearance="account"
        />
        <OfferHistory rounds={offerDetail().rounds} perspective="customer" appearance="account" />
      </>
    );
    expect(screen.getByText("Agreed price")).toBeInTheDocument();
    expect(screen.getByText("Last amount on the table")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("list").tagName).toBe("OL");
  });
});
