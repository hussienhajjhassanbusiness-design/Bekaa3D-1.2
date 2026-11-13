"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { Form } from "@/components/forms/Form";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { usePasswordResetConfirm } from "@/lib/auth/usePasswordResetConfirm";
import { extractResetToken, removeTokenFromUrl } from "@/lib/auth/passwordResetToken";
import { mapValidationErrorsToFields } from "@/lib/api/validationErrors";
import type { ApiError } from "@/lib/api/ApiError";
import { AuthBackToLogin, AuthShell, type AuthCardProps } from "@/components/auth/AuthShell";
import { buttonLinkClassName } from "@/components/forms/Button";

// Phase 2 auth/account batch (FVS-004, confirm half) — identical
// code-point-counted password rule to registration (8-256 Unicode code
// points, no C0/DEL control characters, no composition rules) —
// confirmed to match registration's rule (FRONTEND-BACKEND-RECONCILIATION
// §3 FVS-004: "field rules... match what the plan assumed from
// registration").
const MIN_PASSWORD_CODE_POINTS = 8;
const MAX_PASSWORD_CODE_POINTS = 256;
const C0_MAX_CODE_POINT = 0x1f;
const DEL_CODE_POINT = 0x7f;

function containsControlCharacter(value: string): boolean {
  return [...value].some((char) => {
    const codePoint = char.codePointAt(0) ?? 0;
    return codePoint <= C0_MAX_CODE_POINT || codePoint === DEL_CODE_POINT;
  });
}

const resetPasswordSchema = z.object({
  new_password: z
    .string()
    .min(1, "Password is required")
    .refine((value) => [...value].length >= MIN_PASSWORD_CODE_POINTS, {
      message: `Password must be at least ${MIN_PASSWORD_CODE_POINTS} characters`,
    })
    .refine((value) => [...value].length <= MAX_PASSWORD_CODE_POINTS, {
      message: `Password must be at most ${MAX_PASSWORD_CODE_POINTS} characters`,
    })
    .refine((value) => !containsControlCharacter(value), {
      message: "Password contains characters that aren't allowed",
    }),
});

type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;

const SUCCESS_MESSAGE = "Your password has been reset. Every session was signed out — please log in with your new password.";
const INVALID_LINK_MESSAGE = "This password reset link is invalid, expired, or missing a token.";
const EXPIRED_MESSAGE = "This password reset link has expired. Request a new one.";
// A 400 ("token unknown, already used, or account unusable") is treated
// identically to a missing/malformed link — the backend's own distinction
// between those causes is never surfaced, matching the error-contract
// rule to use frontend-owned, enumeration-safe copy rather than backend
// diagnostic detail.
const USED_OR_INVALID_MESSAGE = "This password reset link is invalid or has already been used. Request a new one.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";
const RATE_LIMIT_MESSAGE_GENERIC = "Too many attempts. Please try again later.";
const RATE_LIMIT_MESSAGE_WITH_WAIT = (seconds: number) => `Too many attempts. Please wait about ${seconds} seconds and try again.`;

type Failure = { kind: "expired" | "invalid" | "generic"; message: string } | null;

function isRecognizedApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function resolveFailure(error: unknown): Failure {
  if (isRecognizedApiError(error)) {
    if (error.kind === "network") {
      return { kind: "generic", message: NETWORK_MESSAGE };
    }
    if (error.kind === "timeout") {
      return { kind: "generic", message: TIMEOUT_MESSAGE };
    }
    if (error.kind === "http" && error.status === 410) {
      return { kind: "expired", message: EXPIRED_MESSAGE };
    }
    // A 400 means the token itself is dead (unknown/used/account
    // unusable) — the dead-link state, with no point retrying the form.
    if (error.kind === "http" && error.status === 400) {
      return { kind: "invalid", message: USED_OR_INVALID_MESSAGE };
    }
    // A 422 is a request-body validation failure, not a dead token — the
    // form stays visible so the user can fix the field and resubmit.
    // Error-contract rule: branch on `code`/`type`, drop loc[0], and show
    // only a frontend-owned safe message — never the backend's own `msg`.
    if (error.kind === "http" && error.status === 422) {
      const fieldErrors = mapValidationErrorsToFields(error.errors);
      const newPasswordError = fieldErrors.find((item) => item.field === "new_password");
      return { kind: "generic", message: newPasswordError?.message ?? GENERIC_FAILURE_MESSAGE };
    }
    if (error.kind === "http" && error.status === 429) {
      return {
        kind: "generic",
        message:
          error.retryAfterSeconds !== undefined
            ? RATE_LIMIT_MESSAGE_WITH_WAIT(error.retryAfterSeconds)
            : RATE_LIMIT_MESSAGE_GENERIC,
      };
    }
  }
  return { kind: "generic", message: GENERIC_FAILURE_MESSAGE };
}

function ResetPasswordFields() {
  const {
    register,
    formState: { errors, isSubmitting },
  } = useFormContext<ResetPasswordFormValues>();

  return (
    <>
      <PasswordField
        label="New password"
        hint="Use 8-256 characters."
        autoComplete="new-password"
        leadingIcon="lock"
        error={errors.new_password?.message}
        {...register("new_password")}
      />
      <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full">
        Reset password
      </Button>
    </>
  );
}

export default function ResetPassword() {
  const { mutateAsync } = usePasswordResetConfirm();
  const router = useRouter();
  // Phase 5A defect 6 (same root cause FVS-002 BATCH 4 fixed on
  // /verify-email): the token lives only in the URL fragment, which never
  // reaches the server. The previous version read window.location.hash in
  // a useState initializer, so the server always rendered the invalid-link
  // alert while the client's first render showed the form: a real
  // hydration mismatch (reproduced in Edge against the dev server).
  //
  // `undefined` means "fragment not read yet". It is the initial value on
  // BOTH the server and the client's hydration render, so their markup is
  // identical. The fragment is then read, and removed from the URL, in one
  // client-only effect. The token lives only in this component's memory:
  // never localStorage/sessionStorage, never logged.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [failure, setFailure] = useState<Failure>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // Capture exactly once per page instance. React Strict Mode re-runs
  // effects in development without resetting refs, and by its second run
  // the fragment has already been removed: re-reading it would wrongly
  // settle on "no token".
  const hasCapturedRef = useRef(false);

  useEffect(() => {
    if (hasCapturedRef.current) {
      return;
    }
    hasCapturedRef.current = true;
    const captured = extractResetToken(window.location.hash);
    // Sanitize the browser-visible URL immediately after capturing the
    // token, regardless of whether one was present — never leave it
    // sitting in the address bar/history entry.
    const sanitized = removeTokenFromUrl(window.location.pathname + window.location.search + window.location.hash);
    window.history.replaceState(null, "", sanitized);
    // Syncing once from an external system (the URL) after mount is the
    // point of this effect; deriving it during render would reintroduce
    // the server/client mismatch.
    setToken(captured);
  }, []);

  useEffect(() => {
    headingRef.current?.focus();
  }, [isSubmitted]);

  async function handleSubmit(values: ResetPasswordFormValues) {
    if (token == null) {
      return;
    }
    setFailure(null);
    try {
      await mutateAsync({ token, new_password: values.new_password });
      setIsSubmitted(true);
    } catch (error) {
      setFailure(resolveFailure(error));
    }
  }

  const showInvalidLink = token === null || failure?.kind === "invalid";
  const showExpired = failure?.kind === "expired";

  // Batch 4 (DERIVED from the A3 forgot-password card). Presentation only:
  // the first render (server and hydration) is still the neutral spinner,
  // and the token is never rendered, stored or put in a URL. The status
  // glyph and description follow the state already computed above; the
  // description never repeats the state words the alerts carry.
  const status: AuthCardProps["status"] =
    token === undefined
      ? undefined
      : isSubmitted
        ? { icon: "check-circle", tone: "success" }
        : showExpired
          ? { icon: "warning", tone: "warning" }
          : showInvalidLink
            ? { icon: "error", tone: "error" }
            : undefined;
  const showForm = token !== undefined && !isSubmitted && !showInvalidLink && !showExpired;

  return (
    <AuthShell
      align="start"
      title="Reset your password"
      titleRef={headingRef}
      status={status}
      description={showForm ? "Choose a new password for your Bekaa3D account." : undefined}
    >
      {token === undefined ? (
        <div className="flex justify-center py-6">
          <LoadingSpinner />
        </div>
      ) : isSubmitted ? (
        <>
          <Alert variant="success" message={SUCCESS_MESSAGE} />
          <Button onClick={() => router.push("/login")} size="lg" className="w-full">
            Log in
          </Button>
        </>
      ) : showInvalidLink || showExpired ? (
        <>
          <Alert
            variant="error"
            message={showExpired ? EXPIRED_MESSAGE : token === null ? INVALID_LINK_MESSAGE : USED_OR_INVALID_MESSAGE}
          />
          <Link href="/forgot-password" className={`w-full ${buttonLinkClassName("primary", "lg")}`}>
            Request a new link
          </Link>
          <AuthBackToLogin />
        </>
      ) : (
        <>
          {failure && <Alert variant="error" message={failure.message} />}
          <Form
            schema={resetPasswordSchema}
            defaultValues={{ new_password: "" }}
            onSubmit={handleSubmit}
            className="flex flex-col gap-5"
          >
            <ResetPasswordFields />
          </Form>
          <AuthBackToLogin />
        </>
      )}
    </AuthShell>
  );
}
