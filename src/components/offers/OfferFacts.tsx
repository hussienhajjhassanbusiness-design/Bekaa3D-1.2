import type { ReactNode } from "react";
import { formatMoney, offerDeadline } from "@/lib/offers/offerModel";
import type { OfferDetailReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// Stitch account styling (Batch 7; the admin offer page adopted it in Batch 10
// and the pre-redesign "default" rendering was removed in Batch 11): mono
// label role, larger values, the money in the bold primary offer role of
// Stitch C3.
const STYLE = {
  list: "grid gap-x-6 gap-y-5 tablet:grid-cols-2 xl:grid-cols-3",
  term: "font-label text-label-sm uppercase tracking-widest text-on-surface-variant",
  value: "mt-1 break-words text-body-md text-on-surface",
  money: "font-label text-title-sm font-bold text-primary",
};

function Fact({ label, money = false, children }: { label: string; money?: boolean; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className={STYLE.term}>{label}</dt>
      <dd className={STYLE.value}>{money ? <span className={STYLE.money}>{children}</span> : children}</dd>
    </div>
  );
}

// #FVS-OFFERS-FACTS (phase 6C). Only the server's own amounts and instants:
// nothing is computed from the list price, and a deadline is display only.
export function OfferFacts({ offer, children }: { offer: OfferDetailReadDTO; children?: ReactNode }) {
  const deadline = offerDeadline(offer);

  return (
    <dl className={STYLE.list}>
      {children}
      <Fact label="First offer" money>
        {formatMoney(offer.initial_amount)}
      </Fact>
      <Fact label={offer.agreed_amount ? "Last amount on the table" : "Amount on the table"} money>
        {formatMoney(offer.current_amount)}
      </Fact>
      {offer.agreed_amount && (
        <Fact label="Agreed price" money>
          {formatMoney(offer.agreed_amount)}
        </Fact>
      )}
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
