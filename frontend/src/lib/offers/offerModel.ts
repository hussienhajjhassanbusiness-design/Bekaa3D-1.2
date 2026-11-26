import type { StatusBadgeTone } from "@/components/admin/StatusBadge";
import type { PriceRead } from "@/lib/catalog/productTypes";
import type { OfferMove, OfferRoundReadDTO, OfferStatus, OfferSummaryReadDTO } from "./offerTypes";

// #FVS-OFFERS-PRESENTATION (phase 6C)
//
// Frontend-owned wording for the server's offer enums. Nothing here decides
// what a party may do: the buttons come only from the server's
// `allowed_actions`, and the checkout panel only from `status: accepted`.
// The enum values themselves are never shown; an unknown value falls back
// to neutral text.

export type OfferPerspective = "customer" | "admin";

// LIVE_STATUSES (negotiation/domain/enums.py): an offer that still blocks a
// new one on the same product (409 OFFER_ALREADY_ACTIVE).
const LIVE: ReadonlySet<string> = new Set<OfferStatus>(["awaiting_admin", "awaiting_customer", "accepted"]);

export function isLiveOffer(status: string): boolean {
  return LIVE.has(status);
}

const STATUS: Record<OfferStatus, Record<OfferPerspective, { label: string; tone: StatusBadgeTone }>> = {
  awaiting_admin: {
    customer: { label: "Waiting for our reply", tone: "neutral" },
    admin: { label: "Your reply needed", tone: "warning" },
  },
  awaiting_customer: {
    customer: { label: "Your reply needed", tone: "warning" },
    admin: { label: "Waiting for the customer", tone: "neutral" },
  },
  accepted: {
    customer: { label: "Accepted: ready to check out", tone: "positive" },
    admin: { label: "Accepted: awaiting checkout", tone: "positive" },
  },
  rejected: { customer: { label: "Declined", tone: "negative" }, admin: { label: "Rejected", tone: "negative" } },
  expired: { customer: { label: "Expired", tone: "neutral" }, admin: { label: "Expired", tone: "neutral" } },
  withdrawn: { customer: { label: "Withdrawn", tone: "neutral" }, admin: { label: "Withdrawn", tone: "neutral" } },
  paid: { customer: { label: "Paid", tone: "positive" }, admin: { label: "Paid", tone: "positive" } },
  checkout_expired: {
    customer: { label: "Checkout window ended", tone: "neutral" },
    admin: { label: "Checkout window ended", tone: "neutral" },
  },
  auto_closed: {
    customer: { label: "Closed: STL bought another way", tone: "neutral" },
    admin: { label: "Closed: STL bought another way", tone: "neutral" },
  },
};

export const OFFER_STATUSES = Object.keys(STATUS) as OfferStatus[];

export function isOfferStatus(value: string): value is OfferStatus {
  return Object.prototype.hasOwnProperty.call(STATUS, value);
}

export function describeOfferStatus(
  status: string,
  perspective: OfferPerspective
): { label: string; tone: StatusBadgeTone } {
  return isOfferStatus(status) ? STATUS[status][perspective] : { label: "Status unavailable", tone: "neutral" };
}

export function formatMoney(price: PriceRead): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: price.currency }).format(
    price.amount_cents / 100
  );
}

// The moves the server says this caller may make now, in a fixed display
// order, restricted to the caller's own move set.
const MOVES: Record<OfferPerspective, readonly OfferMove[]> = {
  customer: ["accept", "counter", "withdraw"],
  admin: ["accept", "counter", "reject"],
};

export function allowedMoves(allowed: readonly string[], perspective: OfferPerspective): OfferMove[] {
  return MOVES[perspective].filter((move) => allowed.includes(move));
}

// Who put `current_amount` on the table: the last customer/admin round that
// carried an amount (submitted or countered). System rounds (paid, expired…)
// are ignored. Null when the history has no such round.
export function offerAmountOwner(rounds: readonly OfferRoundReadDTO[]): "customer" | "admin" | null {
  for (let index = rounds.length - 1; index >= 0; index -= 1) {
    const round = rounds[index]!;
    if (
      round.amount &&
      (round.action === "submitted" || round.action === "countered") &&
      (round.actor === "customer" || round.actor === "admin")
    ) {
      return round.actor;
    }
  }
  return null;
}

// One line of the negotiation history, from the viewer's side.
function party(actor: string, perspective: OfferPerspective): string {
  if (actor === "customer") return perspective === "customer" ? "You" : "Customer";
  if (actor === "admin") return perspective === "customer" ? "Bekaa3D" : "You (Bekaa3D)";
  return "Bekaa3D";
}

export function describeRound(round: OfferRoundReadDTO, perspective: OfferPerspective): string {
  const who = party(round.actor, perspective);
  const amount = round.amount ? formatMoney(round.amount) : null;
  switch (round.action) {
    case "submitted":
      return amount ? `${who} offered ${amount}` : `${who} made an offer`;
    case "countered":
      return amount ? `${who} countered with ${amount}` : `${who} countered`;
    case "accepted":
      return amount ? `${who} accepted ${amount}` : `${who} accepted`;
    case "rejected":
      return `${who} declined the offer`;
    case "withdrawn":
      return `${who} withdrew the offer`;
    case "expired":
      return "The offer expired: the reply deadline passed";
    case "paid":
      return amount ? `Paid ${amount}` : "Paid";
    case "checkout_expired":
      return "The checkout window ended";
    case "auto_closed":
      return "Closed: the STL was bought another way";
    default:
      return "Offer updated";
  }
}

// The deadline that matters now: a reply while someone must answer, the
// checkout window once accepted. Display only; the server enforces both.
export function offerDeadline(
  offer: Pick<OfferSummaryReadDTO, "status" | "responds_by" | "checkout_expires_at">
): { kind: "reply"; at: string } | { kind: "checkout"; at: string } | null {
  if (offer.status === "accepted" && offer.checkout_expires_at)
    return { kind: "checkout", at: offer.checkout_expires_at };
  if ((offer.status === "awaiting_admin" || offer.status === "awaiting_customer") && offer.responds_by) {
    return { kind: "reply", at: offer.responds_by };
  }
  return null;
}

export const UNNAMED_OFFER_PRODUCT = "STL product";

export function offerProductName(name: string | null): string {
  return name ?? UNNAMED_OFFER_PRODUCT;
}
