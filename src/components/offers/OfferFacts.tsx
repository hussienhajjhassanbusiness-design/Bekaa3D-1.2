import type { ReactNode } from "react";
import { formatMoney, offerDeadline } from "@/lib/offers/offerModel";
import type { OfferDetailReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// Presentation only. "default" is the original rendering (still used by
// the admin offer page until its own redesign batch); "account" is the
// Batch 7 customer styling (mono label role, larger values, the money in
// the bold primary offer role of Stitch C3).
export type OfferFactsAppearance = "default" | "account";

const STYLES: Record<OfferFactsAppearance, { list: string; term: string; value: string; money: string }> = {
  default: {
    list: "grid gap-3 tablet:grid-cols-2",
    term: "text-label font-semibold uppercase tracking-label text-text-secondary",
    value: "mt-1 text-body text-text-primary",
    money: "",
  },
  account: {
    list: "grid gap-x-6 gap-y-5 tablet:grid-cols-2 xl:grid-cols-3",
    term: "font-label text-label-sm uppercase tracking-widest text-on-surface-variant",
    value: "mt-1 break-words text-body-md text-on-surface",
    money: "font-label text-title-sm font-bold text-primary",
  },
};

type FactStyle = (typeof STYLES)[OfferFactsAppearance];

function Fact({
  style,
  label,
  money = false,
  children,
}: {
  style: FactStyle;
  label: string;
  money?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className={style.term}>{label}</dt>
      <dd className={style.value}>
        {money && style.money ? <span className={style.money}>{children}</span> : children}
      </dd>
    </div>
  );
}

// #FVS-OFFERS-FACTS (phase 6C). Only the server's own amounts and instants:
// nothing is computed from the list price, and a deadline is display only.
export function OfferFacts({
  offer,
  children,
  appearance = "default",
}: {
  offer: OfferDetailReadDTO;
  children?: ReactNode;
  appearance?: OfferFactsAppearance;
}) {
  const deadline = offerDeadline(offer);
  const style = STYLES[appearance];

  return (
    <dl className={style.list}>
      {children}
      <Fact style={style} label="First offer" money>
        {formatMoney(offer.initial_amount)}
      </Fact>
      <Fact style={style} label={offer.agreed_amount ? "Last amount on the table" : "Amount on the table"} money>
        {formatMoney(offer.current_amount)}
      </Fact>
      {offer.agreed_amount && (
        <Fact style={style} label="Agreed price" money>
          {formatMoney(offer.agreed_amount)}
        </Fact>
      )}
      {deadline && (
        <Fact style={style} label={deadline.kind === "checkout" ? "Check out by" : "Reply by"}>
          <time dateTime={deadline.at}>{formatOrderDateTime(deadline.at)}</time>
        </Fact>
      )}
      {offer.status === "rejected" && offer.cooldown_until && (
        <Fact style={style} label="New offer possible after">
          <time dateTime={offer.cooldown_until}>{formatOrderDateTime(offer.cooldown_until)}</time>
        </Fact>
      )}
      <Fact style={style} label="Opened">
        <time dateTime={offer.created_at}>{formatOrderDateTime(offer.created_at)}</time>
      </Fact>
    </dl>
  );
}
