"use client";

import { useEffect, useRef, useState } from "react";
import { isTerminalPaymentStatus, type PaymentStatus } from "./paymentStatusModel";

export interface UsePaymentStatusPollerOptions {
  status: PaymentStatus | null;
  // REQUIRED — never a built-in production default, mirroring
  // useScanStatusPolling's own `intervalMs`-required precedent
  // exactly (FVS-027-IMPLEMENTATION-PLAN.md T03).
  getDelayMs: (attempt: number) => number;
  maxDurationMs: number;
  onPoll: () => void;
}

export interface UsePaymentStatusPollerResult {
  isTimedOut: boolean;
  retry: () => void;
}

// Mirrors useScanStatusPolling's own "dumb hook, caller does the
// actual work" architecture exactly — extended only with the
// max-duration/timeout concept this slice's own UX-states line
// requires. This hook never fetches or interprets a response; a
// thrown network error during whatever `onPoll` triggers is the
// caller's own concern, surfaced one layer up as
// PaymentVerificationState's "network-error" kind — never a status
// this hook invents.
export function usePaymentStatusPoller({
  status,
  getDelayMs,
  maxDurationMs,
  onPoll,
}: UsePaymentStatusPollerOptions): UsePaymentStatusPollerResult {
  const [isTimedOut, setIsTimedOut] = useState(false);

  const statusRef = useRef(status);
  statusRef.current = status;
  const getDelayMsRef = useRef(getDelayMs);
  getDelayMsRef.current = getDelayMs;
  const maxDurationMsRef = useRef(maxDurationMs);
  maxDurationMsRef.current = maxDurationMs;
  const onPollRef = useRef(onPoll);
  onPollRef.current = onPoll;

  const attemptRef = useRef(0);
  const startTimeRef = useRef(Date.now());
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTimedOutRef = useRef(false);

  function clearScheduled() {
    if (timeoutIdRef.current !== null) {
      clearTimeout(timeoutIdRef.current);
      timeoutIdRef.current = null;
    }
  }

  function scheduleNext() {
    clearScheduled();

    const currentStatus = statusRef.current;
    const isNonTerminal = currentStatus === null || !isTerminalPaymentStatus(currentStatus);
    if (!isNonTerminal || isTimedOutRef.current) {
      return;
    }

    const elapsed = Date.now() - startTimeRef.current;
    const remaining = maxDurationMsRef.current - elapsed;
    if (remaining <= 0) {
      isTimedOutRef.current = true;
      setIsTimedOut(true);
      return;
    }

    // Capped to the remaining budget — independent review found that
    // checking elapsed only before scheduling let a poll fire up to
    // a full backoff interval after maxDurationMs had already
    // elapsed. The capped delay guarantees this timer never fires
    // later than the configured deadline.
    const delay = Math.min(getDelayMsRef.current(attemptRef.current), remaining);
    timeoutIdRef.current = setTimeout(() => {
      if (Date.now() - startTimeRef.current >= maxDurationMsRef.current) {
        isTimedOutRef.current = true;
        setIsTimedOut(true);
        return;
      }
      attemptRef.current += 1;
      onPollRef.current();
      scheduleNext();
    }, delay);
  }

  useEffect(() => {
    scheduleNext();
    return clearScheduled;
    // Intentionally mount-only: scheduleNext reads status/config via
    // refs and re-schedules itself recursively, so it never needs to
    // restart from an effect dependency change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cancel immediately once status becomes terminal, rather than
  // waiting for the next already-scheduled tick to notice.
  useEffect(() => {
    if (status !== null && isTerminalPaymentStatus(status)) {
      clearScheduled();
    }
  }, [status]);

  function retry() {
    startTimeRef.current = Date.now();
    attemptRef.current = 0;
    isTimedOutRef.current = false;
    setIsTimedOut(false);
    scheduleNext();
  }

  return { isTimedOut, retry };
}
