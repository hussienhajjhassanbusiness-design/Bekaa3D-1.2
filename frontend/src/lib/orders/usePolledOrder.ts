"use client";

import { useCallback, useEffect, useState } from "react";
import { useMyOrder } from "./useMyOrders";
import { isPaymentTransient, PAYMENT_POLLING } from "./paymentVerification";

// #FVS027-BOUNDED-PAYMENT-POLLING (phase 5F)
//
// The order detail page's ONE reader of GET /me/orders/{id}: the canonical
// orderKeys.detail(id) query (no separate payment cache), with a
// refetchInterval that is on only while the server itself reports a live
// payment attempt (paymentVerification.isPaymentTransient).
//
//   idle      -> not transient (cash, no payment, terminal payment or order)
//   fast      -> every 3 s for the first 30 s of a window
//   slow      -> every 10 s until 3 min after the window opened
//   timed-out -> stopped; the payment is still unresolved on the server.
//                The page stays usable and offers "Check again", which
//                re-reads now and opens one new bounded window.
//
// The window opens when the data turns transient and closes as soon as it
// is not (a terminal answer stops polling on the very response that
// carries it). While the tab is hidden TanStack pauses the interval
// (refetchIntervalInBackground defaults to false) and refetches on focus.
// One page mounts this hook, so there is one interval at most.
type Phase = "idle" | "fast" | "slow" | "timed-out";

export interface PolledOrder {
  query: ReturnType<typeof useMyOrder>;
  transient: boolean;
  polling: boolean;
  timedOut: boolean;
  checkAgain: () => void;
}

export function usePolledOrder(orderId: string, options: { enabled?: boolean } = {}): PolledOrder {
  const [phase, setPhase] = useState<Phase>("idle");
  // Bumped by checkAgain to restart the window's timers.
  const [windowId, setWindowId] = useState(0);
  const refetchInterval =
    phase === "fast" ? PAYMENT_POLLING.fastIntervalMs : phase === "slow" ? PAYMENT_POLLING.slowIntervalMs : false;
  const query = useMyOrder(orderId, { enabled: options.enabled, refetchInterval });
  const transient = isPaymentTransient(query.data);

  // Adjust the phase while rendering when the server's answer changes
  // (React's "storing information from previous renders" pattern).
  const [seenTransient, setSeenTransient] = useState(false);
  if (transient !== seenTransient) {
    setSeenTransient(transient);
    setPhase(transient ? "fast" : "idle");
  }

  useEffect(() => {
    if (phase === "fast") {
      const timer = setTimeout(() => setPhase("slow"), PAYMENT_POLLING.fastPhaseMs);
      return () => clearTimeout(timer);
    }
    if (phase === "slow") {
      const timer = setTimeout(
        () => setPhase("timed-out"),
        PAYMENT_POLLING.maxDurationMs - PAYMENT_POLLING.fastPhaseMs
      );
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [phase, windowId]);

  const { refetch } = query;
  const checkAgain = useCallback(() => {
    if (transient) {
      setPhase("fast");
      setWindowId((id) => id + 1);
    }
    void refetch();
  }, [transient, refetch]);

  return {
    query,
    transient,
    polling: phase === "fast" || phase === "slow",
    timedOut: phase === "timed-out",
    checkAgain,
  };
}
