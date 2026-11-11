"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { isFollowableRedirect } from "@/lib/checkout/checkoutModel";
import { followPaymentRedirect } from "@/lib/checkout/paymentRedirect";
import { orderKeys } from "./orderKeys";
import { ordersApi } from "./ordersApi";
import { describePaymentRetryError, type PaymentRetryErrorOutcome } from "./paymentRetryErrors";
import { usePaymentRetryTracker } from "./paymentRetryIdempotency";

// #FVS027-RETRY-PAYMENT (phase 5F)
//
// One "Retry payment" press = one logical attempt = one Idempotency-Key
// (paymentRetryIdempotency.ts). The mutation is never retried by itself;
// a resend after an UNCERTAIN outcome is the customer's explicit press and
// reuses the key, any definitive answer retires it.
//
// Duplicate-submit protection: a synchronous ref guard (a double click
// lands before React re-renders the disabled button) plus the pending
// state that disables the control.
//
// Success: the server's `redirect_url` is followed exactly as given, only
// if it is absolute http(s) (checkoutModel.isFollowableRedirect); it is
// never parsed, and nothing local is marked paid. With no followable URL,
// the canonical order detail is re-read and shows the server's state.
// Every settled answer invalidates the canonical order family, never a
// separate payment cache.
export type RetryPaymentState =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "redirecting" }
  | { kind: "started" }
  | { kind: "error"; outcome: PaymentRetryErrorOutcome };

export function useRetryPayment(orderId: string) {
  const queryClient = useQueryClient();
  const tracker = usePaymentRetryTracker();
  const inFlight = useRef(false);
  const [state, setState] = useState<RetryPaymentState>({ kind: "idle" });

  const mutation = useMutation({
    mutationFn: (key: string) => ordersApi.retryPayment(orderId, key),
    retry: false,
  });
  const { mutateAsync } = mutation;

  const start = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ kind: "sending" });
    const key = tracker.keyFor(orderId);
    try {
      const read = await mutateAsync(key);
      tracker.retire();
      void queryClient.invalidateQueries({ queryKey: orderKeys.root });
      const url = read.payment.redirect_url;
      if (isFollowableRedirect(url)) {
        setState({ kind: "redirecting" });
        followPaymentRedirect(url);
        // Stay locked: the browser is leaving for the provider.
        return;
      }
      setState({ kind: "started" });
    } catch (error) {
      const outcome = describePaymentRetryError(error);
      if (!outcome.uncertain) {
        tracker.retire();
      }
      if (outcome.refetchOrder) {
        void queryClient.invalidateQueries({ queryKey: orderKeys.root });
      }
      setState({ kind: "error", outcome });
    }
    inFlight.current = false;
  }, [mutateAsync, orderId, queryClient, tracker]);

  // 409 PAYMENT_ALREADY_ACTIVE: continue the live attempt the server named.
  const resume = useCallback((url: string) => {
    if (!isFollowableRedirect(url)) return;
    inFlight.current = true;
    setState({ kind: "redirecting" });
    followPaymentRedirect(url);
  }, []);

  return { state, start, resume };
}
