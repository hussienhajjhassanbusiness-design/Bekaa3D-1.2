"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Alert } from "@/components/feedback/Alert";
import { useVerifyEmail } from "@/lib/auth/useVerifyEmail";
import type { ApiError } from "@/lib/api/ApiError";

// FVS-002-IMPLEMENTATION-PLAN.md §1 row 8 (confirmed at BATCH 2): the
// verification token travels in the URL FRAGMENT (#token=...), never a
// query string — `useSearchParams()` cannot see a fragment, so it is never
// used here. Read once, client-side only, via window.location.hash.
const TOKEN_LENGTH = 43;

// Exported for direct unit testing. Uses URLSearchParams over the fragment
// body (percent-decoding included) rather than a hand-rolled parser —
// handles a missing/empty hash, a missing token key, an empty token value,
// and unrelated fragment fields safely, without ever throwing.
export function parseTokenFromHash(hash: string): string | undefined {
  const withoutLeadingHash = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!withoutLeadingHash) {
    return undefined;
  }
  const params = new URLSearchParams(withoutLeadingHash);
  const token = params.get("token");
  return token ? token : undefined;
}

// §1 row 8: token length is confirmed as exactly 43 characters. No
// alphabet/regex is invented beyond that — the backend never confirmed one
// (bekaa3d-api-contract: never invent an unconfirmed shape).
function hasValidTokenShape(token: string | undefined): token is string {
  return typeof token === "string" && token.length === TOKEN_LENGTH;
}

type Status = "verifying" | "success" | "invalid" | "expired" | "rateLimited" | "network" | "timeout" | "failed";

const INVALID_MESSAGE = "This verification link isn't valid. Request a new one.";
const EXPIRED_MESSAGE =
  "This link has expired. If you already verified your email, log in. Otherwise, request a new link.";
const RATE_LIMIT_MESSAGE = "Too many attempts. Please wait a bit and try again.";
const RATE_LIMIT_MESSAGE_WITH_WAIT = (seconds: number) =>
  `Too many attempts. Please wait about ${seconds} seconds and try again.`;
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";

function isRecognizedApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function statusFromError(error: unknown): Status {
  if (isRecognizedApiError(error)) {
    if (error.kind === "http" && error.status === 400) {
      return "invalid";
    }
    if (error.kind === "http" && error.status === 410) {
      return "expired";
    }
    if (error.kind === "http" && error.status === 429) {
      return "rateLimited";
    }
    if (error.kind === "network") {
      return "network";
    }
    if (error.kind === "timeout") {
      return "timeout";
    }
  }
  return "failed";
}

export default function VerifyEmail() {
  const { mutateAsync } = useVerifyEmail();
  // Single-consumption guard: the token is single-use, so at most one POST
  // may ever fire per page instance — including under React Strict Mode's
  // dev-only double-invoke of effects, which does not reset an existing ref
  // object between its cleanup+re-run cycle. "useEffect has []" alone is not
  // this guard; the ref is.
  const hasFiredRef = useRef(false);
  const [token] = useState<string | undefined>(() =>
    typeof window === "undefined" ? undefined : parseTokenFromHash(window.location.hash)
  );
  const [status, setStatus] = useState<Status>(() => (hasValidTokenShape(token) ? "verifying" : "invalid"));
  const [retryAfterSeconds, setRetryAfterSeconds] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (hasFiredRef.current) {
      return;
    }
    if (!hasValidTokenShape(token)) {
      // Local validation failure: never call the backend (§ fragment
      // parsing rules) — the safe invalid state is already the initial
      // state above.
      return;
    }
    hasFiredRef.current = true;
    mutateAsync({ token })
      .then(() => setStatus("success"))
      .catch((error: unknown) => {
        if (isRecognizedApiError(error) && error.kind === "http" && error.status === 429) {
          setRetryAfterSeconds(error.retryAfterSeconds);
        }
        setStatus(statusFromError(error));
      });
    // token is fixed for the life of this page instance (read once above);
    // mutateAsync is intentionally excluded — re-including it would risk a
    // second fire if the mutation hook ever returns a new function identity,
    // which the ref guard above already protects against regardless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (status === "verifying") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <LoadingSpinner />
      </>
    );
  }

  if (status === "success") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert variant="success" message="Your email is verified." />
        <p className="mt-4">
          <Link href="/login" className="text-text-link underline">
            Log in
          </Link>
        </p>
      </>
    );
  }

  if (status === "expired") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert variant="error" message={EXPIRED_MESSAGE} />
        <p className="mt-4 flex gap-4">
          <Link href="/login" className="text-text-link underline">
            Log in
          </Link>
          <Link href="/verify-email/resend" className="text-text-link underline">
            Request a new link
          </Link>
        </p>
      </>
    );
  }

  if (status === "rateLimited") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert
          variant="warning"
          message={retryAfterSeconds !== undefined ? RATE_LIMIT_MESSAGE_WITH_WAIT(retryAfterSeconds) : RATE_LIMIT_MESSAGE}
        />
      </>
    );
  }

  if (status === "network") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert variant="error" message={NETWORK_MESSAGE} />
      </>
    );
  }

  if (status === "timeout") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert variant="error" message={TIMEOUT_MESSAGE} />
      </>
    );
  }

  if (status === "failed") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
        <Alert variant="error" message={GENERIC_FAILURE_MESSAGE} />
      </>
    );
  }

  // status === "invalid" — also covers local-validation failure, 400
  // INVALID_TOKEN (invalid/used/already-verified all intentionally
  // collapse here per §13's confirmed mapping — never a separate state).
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Verify your email</h1>
      <Alert variant="error" message={INVALID_MESSAGE} />
      <p className="mt-4">
        <Link href="/verify-email/resend" className="text-text-link underline">
          Request a new link
        </Link>
      </p>
    </>
  );
}
