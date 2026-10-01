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
  // FVS-002 BATCH 4 Part C — same success-focus fix as the register page:
  // move focus to the success heading once status flips to "success", so
  // it never silently lands on <body>.
  const successHeadingRef = useRef<HTMLHeadingElement>(null);
  // Single-consumption guard: the token is single-use, so at most one POST
  // may ever fire per page instance — including under React Strict Mode's
  // dev-only double-invoke of effects, which does not reset an existing ref
  // object between its cleanup+re-run cycle. "useEffect has []" alone is not
  // this guard; the ref is.
  const hasFiredRef = useRef(false);
  // FVS-002 BATCH 4 Part A finding: `status` must start at the SAME value
  // on the server and the client. The previous version read
  // window.location.hash inside a useState initializer to pick the
  // initial status ("verifying" vs "invalid") — since `window` doesn't
  // exist during server rendering, the server always rendered "invalid"
  // while the client's very first render (before this effect ever runs)
  // could render "verifying" instead, a genuine React hydration mismatch
  // (observed directly via Playwright/Edge against the real Next.js dev
  // server, not merely theorized). Fixed by never branching on `window`
  // during render: `status` always starts at "verifying" on both sides,
  // and every window-dependent decision — parsing the fragment, clearing
  // it, firing the request — happens inside one client-only effect below.
  const [status, setStatus] = useState<Status>("verifying");
  const [retryAfterSeconds, setRetryAfterSeconds] = useState<number | undefined>(undefined);

  // Single effect, client-only, runs once: parses the fragment, clears it
  // from the visible URL (Part F — the secret must not linger in
  // window.location.hash for the page's lifetime), then either fires the
  // one-time verify request or settles on the invalid state — all from one
  // locally-captured token value, never re-reading location.hash after
  // it's been cleared. The hasFiredRef guard (not reset in cleanup) still
  // protects against a second POST under React Strict Mode's dev-only
  // double-invoke of effects.
  useEffect(() => {
    if (hasFiredRef.current) {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }

    // The capture/clear/decide logic itself runs inside this nested async
    // function, not directly in the effect body — every setState call
    // below is this function reacting to something it just did (read the
    // fragment, awaited the mutation), not the effect synchronously
    // deriving render state on every commit (the lint rule's actual
    // target; this runs at most once, guarded by hasFiredRef).
    async function captureAndVerify() {
      const parsedToken = parseTokenFromHash(window.location.hash);

      if (window.location.hash) {
        window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
      }

      if (!hasValidTokenShape(parsedToken)) {
        // Local validation failure: never call the backend.
        setStatus("invalid");
        return;
      }

      hasFiredRef.current = true;
      try {
        await mutateAsync({ token: parsedToken });
        setStatus("success");
      } catch (error) {
        if (isRecognizedApiError(error) && error.kind === "http" && error.status === 429) {
          setRetryAfterSeconds(error.retryAfterSeconds);
        }
        setStatus(statusFromError(error));
      }
    }

    void captureAndVerify();
    // mutateAsync is intentionally excluded — re-including it would risk a
    // second fire if the mutation hook ever returns a new function
    // identity, which the ref guard above already protects against
    // regardless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status === "success") {
      successHeadingRef.current?.focus();
    }
  }, [status]);

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
        <h1 ref={successHeadingRef} tabIndex={-1} className="text-h1 font-bold text-text-primary">
          Verify your email
        </h1>
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
