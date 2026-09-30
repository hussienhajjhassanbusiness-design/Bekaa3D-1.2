"use client";

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { useResendVerification } from "@/lib/auth/useResendVerification";
import { useCooldown } from "@/lib/auth/useCooldown";
import type { ApiError } from "@/lib/api/ApiError";

// FVS-002-IMPLEMENTATION-PLAN.md §1 row 14 (confirmed at BATCH 2): a fixed
// 120-second cooldown starts after EVERY successful 202 — never inferred
// from a response field (none carries it).
const SUCCESS_COOLDOWN_MS = 120_000;

// §9/§1 row 4 — same generic, non-authoritative email-shape rule already
// established by registration; no new rule invented here.
const resendSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email address"),
});

type ResendFormValues = z.infer<typeof resendSchema>;

// §2 — identical copy regardless of whether the backend implies the
// account exists, doesn't exist, or silently suppressed the email because
// its own server-side cooldown is active. The backend's own `message`
// field is never read or rendered.
const SUCCESS_MESSAGE = "If an account exists for that email, a verification email was sent.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";
const RATE_LIMIT_MESSAGE_GENERIC = "Too many attempts. Please try again later.";
const COMPLETION_ANNOUNCEMENT = "You can resend the verification email now.";

function isRecognizedApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

// A safe, non-spammy wait message for a 429 whose Retry-After may be much
// larger than the normal 120-second cooldown (§ rate limit contract) —
// never displays a raw second count once it's large enough to be
// unreadable at a glance.
function formatWaitDuration(seconds: number): string {
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (seconds >= 60) {
    const minutes = Math.round(seconds / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${seconds} seconds`;
}

// Static screen-reader text equivalent to "Resend available at HH:MM:SS",
// derived from the absolute deadline and using the browser's local time
// (§ countdown accessibility — no business timezone is invented for this
// short relative interaction). 24-hour, zero-padded for deterministic
// tests; stable for as long as the deadline itself doesn't change.
function formatLocalTime(timestampMs: number): string {
  const date = new Date(timestampMs);
  const pad = (value: number) => value.toString().padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

type Failure = "network" | "timeout" | "failed" | "rateLimitedNoDuration" | null;

function ResendFields({ disabled }: { disabled: boolean }) {
  const {
    register,
    formState: { errors },
  } = useFormContext<ResendFormValues>();

  return (
    <>
      <TextField
        label="Email"
        // type="text", not "email" — same reasoning as registration: an
        // <input type="email"> auto-trims its own value, which could
        // silently alter what's submitted.
        type="text"
        inputMode="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register("email")}
      />
      <Button type="submit" className="mt-4" disabled={disabled}>
        Resend verification email
      </Button>
    </>
  );
}

export default function ResendVerification() {
  const { mutateAsync } = useResendVerification();
  const [deadline, setDeadline] = useState<number | undefined>(undefined);
  const [deadlineReason, setDeadlineReason] = useState<"success" | "rateLimit" | undefined>(undefined);
  const [failure, setFailure] = useState<Failure>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  const { remainingSeconds, isActive } = useCooldown(deadline);

  // §countdown accessibility — exactly two announcements (start,
  // completion), never once per tick. `isActive` only flips at those two
  // boundaries (useCooldown.ts), so watching its transitions here — rather
  // than remainingSeconds, which changes every second — is what keeps this
  // from spamming the live region.
  const wasActiveRef = useRef(false);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");

  useEffect(() => {
    if (isActive && !wasActiveRef.current && deadline !== undefined) {
      setLiveAnnouncement(`Resend available at ${formatLocalTime(deadline)}.`);
    }
    if (!isActive && wasActiveRef.current) {
      setLiveAnnouncement(COMPLETION_ANNOUNCEMENT);
    }
    wasActiveRef.current = isActive;
  }, [isActive, deadline]);

  async function handleSubmit(values: ResendFormValues) {
    setFailure(null);
    try {
      await mutateAsync(values);
      setShowSuccess(true);
      setDeadlineReason("success");
      setDeadline(Date.now() + SUCCESS_COOLDOWN_MS);
    } catch (error) {
      if (isRecognizedApiError(error) && error.kind === "http" && error.status === 429) {
        if (error.retryAfterSeconds !== undefined) {
          setDeadlineReason("rateLimit");
          setDeadline(Date.now() + error.retryAfterSeconds * 1000);
        } else {
          // § rate limit — missing/malformed Retry-After: show a generic
          // rate-limit failure without inventing a duration. No deadline is
          // set, so the resend button is not disabled by this path.
          setFailure("rateLimitedNoDuration");
        }
        return;
      }
      if (isRecognizedApiError(error) && error.kind === "network") {
        setFailure("network");
        return;
      }
      if (isRecognizedApiError(error) && error.kind === "timeout") {
        setFailure("timeout");
        return;
      }
      setFailure("failed");
    }
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Resend verification email</h1>

      {showSuccess && <Alert variant="success" message={SUCCESS_MESSAGE} />}
      {failure === "network" && <Alert variant="error" message={NETWORK_MESSAGE} />}
      {failure === "timeout" && <Alert variant="error" message={TIMEOUT_MESSAGE} />}
      {failure === "failed" && <Alert variant="error" message={GENERIC_FAILURE_MESSAGE} />}
      {failure === "rateLimitedNoDuration" && <Alert variant="warning" message={RATE_LIMIT_MESSAGE_GENERIC} />}
      {deadlineReason === "rateLimit" && isActive && (
        <Alert
          variant="warning"
          message={`Too many attempts. Please wait about ${formatWaitDuration(remainingSeconds)} and try again.`}
        />
      )}

      {/* Exactly two announcements ever land here: cooldown start, cooldown
          completion — never a per-tick update (see the effect above). */}
      <div aria-live="polite" data-testid="resend-live-region" className="sr-only">
        {liveAnnouncement}
      </div>

      <Form schema={resendSchema} defaultValues={{ email: "" }} onSubmit={handleSubmit} className="mt-4 max-w-[420px]">
        <ResendFields disabled={isActive} />
      </Form>

      {isActive && (
        // Visible ticking countdown — deliberately NOT an aria-live region,
        // so it never spams screen readers on every tick (the live region
        // above is the only aria-live element on this page).
        <p data-testid="resend-countdown-ticking" className="mt-2 text-caption text-text-secondary">
          {deadlineReason === "rateLimit"
            ? `You can try again in about ${formatWaitDuration(remainingSeconds)}.`
            : `Resend available in ${remainingSeconds} seconds.`}
        </p>
      )}
    </>
  );
}
