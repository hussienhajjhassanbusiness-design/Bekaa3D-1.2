import { describeRound, type OfferPerspective } from "@/lib/offers/offerModel";
import type { OfferRoundReadDTO } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// #FVS-OFFERS-HISTORY (phase 6C). The server's append-only round history,
// oldest first, from the viewer's side. Messages are the parties' own text,
// rendered as plain React text (pre-wrap), never as HTML.
export function OfferHistory({ rounds, perspective }: { rounds: readonly OfferRoundReadDTO[]; perspective: OfferPerspective }) {
  const ordered = [...rounds].sort((a, b) => a.sequence - b.sequence);
  return (
    <section aria-labelledby="offer-history-heading" className="flex flex-col gap-3">
      <h2 id="offer-history-heading" className="text-h3 font-semibold text-text-primary">
        History
      </h2>
      {ordered.length === 0 ? (
        <p className="text-body text-text-secondary">No history yet.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {ordered.map((round) => (
            <li key={round.sequence} className="rounded-md border border-border-default bg-white p-3">
              <p className="text-body font-semibold text-text-primary">{describeRound(round, perspective)}</p>
              <p className="text-caption text-text-secondary">
                <time dateTime={round.created_at}>{formatOrderDateTime(round.created_at)}</time>
              </p>
              {round.message && (
                <p className="mt-2 whitespace-pre-wrap break-words text-body text-text-primary">{round.message}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
