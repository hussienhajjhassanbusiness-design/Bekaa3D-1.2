import type { ReactNode } from "react";
import { formatMoney, offerDeadline } from "@/lib/offers/offerModel";
import type { OfferDetailReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-label font-semibold uppercase tracking-label text-text-secondary">{label}</dt>
      <dd className="mt-1 text-body text-text-primary">{children}</dd>
    </div>
  );
}

// #FVS-OFFERS-FACTS (phase 6C). Only the server's own amounts and instants:
// nothing is computed from the list price, and a deadline is display only.
export function OfferFacts({ offer, children }: { offer: OfferDetailReadDTO; children?: ReactNode }) {
  const deadline = offerDeadline(offer);
  return (
    <dl className="grid gap-3 tablet:grid-cols-2">
      {children}
      <Fact label="First offer">{formatMoney(offer.initial_amount)}</Fact>
      <Fact label={offer.agreed_amount ? "Last amount on the table" : "Amount on the table"}>
        {formatMoney(offer.current_amount)}
      </Fact>
      {offer.agreed_amount && <Fact label="Agreed price">{formatMoney(offer.agreed_amount)}</Fact>}
      {deadline && (
        <Fact label={deadline.kind === "checkout" ? "Check out by" : "Reply by"}>
          <time dateTime={deadline.at}>{formatOrderDateTime(deadline.at)}</time>
        </Fact>
      )}
      {offer.status === "rejected" && offer.cooldown_until && (
        <Fact label="New offer possible after">
          <time dateTime={offer.cooldown_until}>{formatOrderDateTime(offer.cooldown_until)}</time>
        </Fact>
      )}
      <Fact label="Opened">
        <time dateTime={offer.created_at}>{formatOrderDateTime(offer.created_at)}</time>
      </Fact>
    </dl>
  );
}
