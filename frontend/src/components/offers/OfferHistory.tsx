import { ACCOUNT_CARD } from "@/components/account/accountUi";
import { describeRound, type OfferPerspective } from "@/lib/offers/offerModel";
import type { OfferRoundReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// #FVS-OFFERS-HISTORY (phase 6C). The server's append-only round history,
// oldest first, from the viewer's side. Messages are the parties' own text,
// rendered as plain React text (pre-wrap), never as HTML.
//
// Stitch §45 timeline + C3's quoted responses (Batch 7; the pre-redesign
// "default" rendering was removed in Batch 11 once the admin offer page
// adopted this one): a card with an ordered list on a decorative rail.
// Still an <ol>, oldest first; who acted and
// what happened are always text.
export function OfferHistory({
  rounds,
  perspective,
}: {
  rounds: readonly OfferRoundReadDTO[];
  perspective: OfferPerspective;
}) {
  const ordered = [...rounds].sort((a, b) => a.sequence - b.sequence);

  return (
    <section aria-labelledby="offer-history-heading" className={`${ACCOUNT_CARD} flex flex-col gap-4 p-5 tablet:p-6`}>
      <h2 id="offer-history-heading" className="font-headline text-headline-md text-on-surface">
        History
      </h2>
      {ordered.length === 0 ? (
        <p className="text-body-md text-on-surface-variant">No history yet.</p>
      ) : (
        <ol className="flex flex-col">
          {ordered.map((round, index) => {
            const ours = round.actor === "customer" ? perspective === "customer" : perspective === "admin";
            return (
              <li key={round.sequence} className="relative flex gap-4 pb-6 last:pb-0">
                <span aria-hidden="true" className="relative flex w-3 shrink-0 justify-center">
                  <span
                    className={`mt-1.5 h-3 w-3 rounded-full border-2 ${
                      ours ? "border-primary bg-primary" : "border-outline bg-surface-container-lowest"
                    }`}
                  />
                  {index < ordered.length - 1 && (
                    <span className="absolute bottom-[-1.5rem] top-5 w-0.5 bg-outline-variant/50" />
                  )}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p className="break-words text-title-sm text-on-surface">{describeRound(round, perspective)}</p>
                  <p className="font-label text-label-caps uppercase text-on-surface-variant">
                    <time dateTime={round.created_at}>{formatOrderDateTime(round.created_at)}</time>
                  </p>
                  {round.message && (
                    <p className="mt-2 whitespace-pre-wrap break-words rounded-control border-l-4 border-outline-variant bg-surface-container-low px-4 py-3 text-body-md italic text-on-surface-variant">
                      {round.message}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
