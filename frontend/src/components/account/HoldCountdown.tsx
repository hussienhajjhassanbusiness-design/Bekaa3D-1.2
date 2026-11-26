"use client";

import { useEffect, useRef, useState } from "react";

export interface HoldCountdownProps {
  // The server's `hold_expires_at` (ISO 8601).
  expiresAt: string;
  // Called once when the countdown reaches zero, so the page can re-read
  // the order. Nothing is changed locally.
  onElapsed?: () => void;
}

// #FVS027-HOLD-COUNTDOWN (phase 5F)
//
// Presentation only. The server's `hold_expires_at` is authoritative
// (`max(placed_at, latest attempt) + checkout_hold_period`, backend
// docs/payment-recovery.md); this device's clock only drives the display.
// Reaching zero mutates nothing and claims nothing: the order is released
// by the backend job only when the provider says failed/expired, and a
// payment completed at the provider can still land. At zero the page
// re-reads the order once and the copy stays conditional.
function remainingMs(expiresAt: number, now: number): number {
  return Math.max(0, expiresAt - now);
}

function format(ms: number): string {
  const total = Math.ceil(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mm = String(minutes).padStart(hours > 0 ? 2 : 1, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function HoldCountdown({ expiresAt, onElapsed }: HoldCountdownProps) {
  const target = Date.parse(expiresAt);
  const [now, setNow] = useState(() => Date.now());
  const fired = useRef(false);
  const valid = Number.isFinite(target);
  const left = valid ? remainingMs(target, now) : 0;
  const done = left === 0;

  // One 1 s ticker while time remains; none once it is up.
  useEffect(() => {
    if (!valid || done) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [valid, done]);

  useEffect(() => {
    if (valid && done && !fired.current) {
      fired.current = true;
      onElapsed?.();
    }
  }, [valid, done, onElapsed]);

  if (!valid) return null;

  if (done) {
    return (
      <p className="rounded-control bg-surface-container-lowest/70 px-3 py-2 text-body-md">
        The time to complete payment is up. If your payment wasn&apos;t completed, this order may be released; its
        status here updates once that happens.
      </p>
    );
  }

  // Batch 7: the remaining time in a mono readout. Still plain text — not a
  // live region and not the order's status (the server decides that).
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 rounded-control bg-surface-container-lowest/70 px-3 py-2 text-body-md">
      Time left to complete payment:{" "}
      <span
        className="font-label text-headline-md font-bold tabular-nums"
        aria-label={`about ${Math.ceil(left / 60_000)} minutes`}
      >
        {format(left)}
      </span>
    </p>
  );
}
