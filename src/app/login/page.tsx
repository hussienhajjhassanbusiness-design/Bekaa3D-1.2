"use client";

import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { z } from "zod";
import { useFormContext } from "react-hook-form";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Form } from "@/components/forms/Form";
import { TextField } from "@/components/forms/TextField";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { useLogin, type LoginResult } from "@/lib/auth/useLogin";
import { useMfaVerify } from "@/lib/auth/useMfaVerify";
import { useCooldown } from "@/lib/auth/useCooldown";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { clearUserScopedQueries } from "@/lib/auth/userScopedQueries";
import { resolveReturnTo } from "@/lib/auth/returnTo";
import { AuthShell, AUTH_INLINE_LINK_CLASSES } from "@/components/auth/AuthShell";

// FVS-003-IMPLEMENTATION-PLAN.md §2 rows 2/3/4b (confirmed BATCH 3B) —
// email is trimmed before submission (the one field-level transformation
// this slice applies, backend-recommended); password is never trimmed and
// does not reuse registration's 8-character minimum (a login form must
// accept any password the backend would, including a shorter pre-existing
// one). The ≤256 cap exactly mirrors the confirmed backend maximum (row 3)
// rather than inventing a new rule.
const MAX_PASSWORD_CODE_POINTS = 256;

const loginSchema = z.object({
  email: z.string().trim().min(1, "Email is required").email("Enter a valid email address"),
  password: z
    .string()
    .min(1, "Password is required")
    .refine((value) => [...value].length <= MAX_PASSWORD_CODE_POINTS, {
      message: `Password must be at most ${MAX_PASSWORD_CODE_POINTS} characters`,
    }),
});

type LoginFormValues = z.infer<typeof loginSchema>;

// §12/§2 rows 8/9/9b — safe, frontend-authored copy only; never the raw
// backend body. INVALID_CREDENTIALS is intentionally identical regardless
// of whether the email is unknown or the password is wrong (enumeration
// safety is a backend-confirmed design intent here, not just a frontend
// convention).
const INVALID_CREDENTIALS_MESSAGE = "Invalid email or password.";
const ACCOUNT_DISABLED_MESSAGE = "Unable to sign in to this account.";
const RATE_LIMIT_MESSAGE_GENERIC = "Too many attempts. Please try again later.";
const RATE_LIMIT_MESSAGE_WITH_WAIT = (seconds: number) => `Too many attempts. Please wait about ${seconds} seconds and try again.`;
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";
// Phase 3 (FVS-005/P1-2) — real MFA verify-step copy. challenge_id is
// never rendered anywhere, including in these messages. A wrong code or
// an expired challenge both force a fresh login — never a retry against
// the same (now-burned, or expired) challenge_id.
const MFA_INVALID_MESSAGE = "That code didn't work. Please log in again to get a new verification code.";
const MFA_EXPIRED_MESSAGE = "Your verification session expired. Please log in again.";
const MFA_ACCOUNT_DISABLED_MESSAGE = "Unable to sign in to this account.";
const MFA_GENERIC_FAILURE_MESSAGE = "Something went wrong verifying your code. Please try again.";

interface MfaChallengeState {
  challengeId: string;
  deadline: number;
}

function mfaFailureMessage(error: unknown): { message: string; resetToLogin: boolean } {
  if (isRecognizedError(error)) {
    if (error.kind === "http" && error.code === "MFA_INVALID") {
      return { message: MFA_INVALID_MESSAGE, resetToLogin: true };
    }
    if (error.kind === "http" && error.code === "RESOURCE_EXPIRED") {
      return { message: MFA_EXPIRED_MESSAGE, resetToLogin: true };
    }
    if (error.kind === "http" && error.code === "ACCOUNT_DISABLED") {
      return { message: MFA_ACCOUNT_DISABLED_MESSAGE, resetToLogin: true };
    }
    if (error.kind === "http" && error.code === "RATE_LIMITED") {
      const message =
        error.retryAfterSeconds !== undefined
          ? RATE_LIMIT_MESSAGE_WITH_WAIT(error.retryAfterSeconds)
          : RATE_LIMIT_MESSAGE_GENERIC;
      return { message, resetToLogin: false };
    }
    if (error.kind === "network") {
      return { message: NETWORK_MESSAGE, resetToLogin: false };
    }
    if (error.kind === "timeout") {
      return { message: TIMEOUT_MESSAGE, resetToLogin: false };
    }
  }
  return { message: MFA_GENERIC_FAILURE_MESSAGE, resetToLogin: false };
}

const MFA_CODE_EXPIRED_COPY = "This code has expired.";

// Batch 11 (countdown accessibility): the spoken form of the time left when
// the challenge starts — minutes for anything a minute or longer, so the
// one announcement is short ("Code expires in 5 minutes.").
function describeMfaTimeLeft(seconds: number): string {
  if (seconds < 60) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.round(seconds / 60);
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

interface MfaVerifyStepProps {
  challenge: MfaChallengeState;
  onVerified: () => void;
  onResetToLogin: (message: string) => void;
}

// #FVS005-MFA-LOGIN-VERIFY
//
// challenge_id lives only in this component's (and its parent's) React
// state — never a URL param, never localStorage/sessionStorage, never
// logged. A wrong code or an expired challenge both call onResetToLogin,
// which discards this component (and the challenge_id with it) entirely
// — there is no "try again" path that resubmits the same challenge_id,
// matching the backend's single-use-challenge contract.
function MfaVerifyStep({ challenge, onVerified, onResetToLogin }: MfaVerifyStepProps) {
  const { mutateAsync } = useMfaVerify();
  const [mode, setMode] = useState<"code" | "recovery">("code");
  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  // Pending state for the Verify button (Batch 4). It also stops a second
  // click from re-sending the same single-use challenge while the first
  // request is in flight; the request itself is unchanged.
  const [isVerifying, setIsVerifying] = useState(false);
  const { remainingSeconds, isActive } = useCooldown(challenge.deadline);

  // Batch 11 — countdown accessibility (same pattern as the resend page).
  // The visible countdown still updates every second, but it is no longer
  // a live region: that re-announced it on every tick. A separate polite
  // sr-only region speaks exactly twice — the time left when the step
  // appears, and the moment the code expires. `isActive` flips only at
  // those boundaries (useCooldown), so watching it, never remainingSeconds,
  // is what keeps the announcements from repeating. Countdown semantics
  // and the challenge itself are unchanged.
  const wasActiveRef = useRef<boolean | null>(null);
  const [countdownAnnouncement, setCountdownAnnouncement] = useState("");
  useEffect(() => {
    const previous = wasActiveRef.current;
    wasActiveRef.current = isActive;
    if (previous === null) {
      const secondsLeft = Math.max(0, Math.ceil((challenge.deadline - Date.now()) / 1000));
      setCountdownAnnouncement(
        isActive ? `Code expires in ${describeMfaTimeLeft(secondsLeft)}.` : MFA_CODE_EXPIRED_COPY
      );
    } else if (previous && !isActive) {
      setCountdownAnnouncement(MFA_CODE_EXPIRED_COPY);
    }
  }, [isActive, challenge.deadline]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (isVerifying) {
      return;
    }
    setFailure(null);
    setIsVerifying(true);
    try {
      if (mode === "code") {
        await mutateAsync({ challenge_id: challenge.challengeId, code });
      } else {
        await mutateAsync({ challenge_id: challenge.challengeId, recovery_code: recoveryCode });
      }
      onVerified();
    } catch (error) {
      const { message, resetToLogin } = mfaFailureMessage(error);
      if (resetToLogin) {
        onResetToLogin(message);
      } else {
        setFailure(message);
      }
    } finally {
      setIsVerifying(false);
    }
  }

  // Batch 4: same auth card as the password step (A1), with the A4 admin
  // card's lock glyph and a mono code input (BEKAA3D-ROUTE-MIGRATION row
  // 10). Copy avoids the word "verification" outside the field label: the
  // label is the one place that names the code.
  return (
    <AuthShell
      showBrand
      title="Two-factor authentication"
      status={{ icon: "lock", tone: "info" }}
      description={
        mode === "code"
          ? "Enter the code from your authenticator app to finish logging in."
          : "Enter one of the recovery codes you saved when you set up two-factor authentication."
      }
    >
      {failure && <Alert variant="error" message={failure} />}
      <form onSubmit={handleSubmit} className="flex flex-col">
        {mode === "code" ? (
          <TextField
            label="Verification code"
            inputMode="numeric"
            autoComplete="one-time-code"
            mono
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        ) : (
          <TextField
            label="Recovery code"
            autoComplete="off"
            mono
            value={recoveryCode}
            onChange={(event) => setRecoveryCode(event.target.value)}
          />
        )}
        <p className="mt-2 text-xs text-on-surface-variant" data-testid="mfa-countdown">
          {isActive ? `Code expires in ${remainingSeconds} seconds.` : MFA_CODE_EXPIRED_COPY}
        </p>
        <p aria-live="polite" data-testid="mfa-countdown-live-region" className="sr-only">
          {countdownAnnouncement}
        </p>
        <Button type="submit" size="lg" isLoading={isVerifying} className="mt-6 w-full">
          Verify
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="mt-2 w-full"
          onClick={() => setMode((current) => (current === "code" ? "recovery" : "code"))}
        >
          {mode === "code" ? "Use a recovery code instead" : "Use my verification code instead"}
        </Button>
      </form>
    </AuthShell>
  );
}

interface RecognizedError {
  kind: string;
  status?: number;
  code?: string;
  retryAfterSeconds?: number;
}

function isRecognizedError(value: unknown): value is RecognizedError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function failureMessage(error: unknown): string {
  if (isRecognizedError(error)) {
    if (error.kind === "http" && error.code === "INVALID_CREDENTIALS") {
      return INVALID_CREDENTIALS_MESSAGE;
    }
    if (error.kind === "http" && error.code === "ACCOUNT_DISABLED") {
      return ACCOUNT_DISABLED_MESSAGE;
    }
    if (error.kind === "http" && error.code === "RATE_LIMITED") {
      return error.retryAfterSeconds !== undefined
        ? RATE_LIMIT_MESSAGE_WITH_WAIT(error.retryAfterSeconds)
        : RATE_LIMIT_MESSAGE_GENERIC;
    }
    if (error.kind === "network") {
      return NETWORK_MESSAGE;
    }
    if (error.kind === "timeout") {
      return TIMEOUT_MESSAGE;
    }
  }
  return GENERIC_FAILURE_MESSAGE;
}

function LoginFields() {
  const {
    register,
    formState: { errors, isSubmitting },
  } = useFormContext<LoginFormValues>();

  return (
    <>
      <TextField
        label="Email"
        type="text"
        inputMode="email"
        autoComplete="email"
        leadingIcon="mail"
        error={errors.email?.message}
        {...register("email")}
      />
      <PasswordField
        label="Password"
        autoComplete="current-password"
        leadingIcon="lock"
        error={errors.password?.message}
        {...register("password")}
      />
      {/* Stitch A1 actions row, without "Remember me" (no such feature):
          a plain link to the existing reset flow. */}
      <div className="-mt-2 flex justify-end">
        <Link href="/forgot-password" className={`inline-flex min-h-11 items-center text-body-md ${AUTH_INLINE_LINK_CLASSES}`}>
          Forgot password?
        </Link>
      </div>
      {/* isLoading only shows the spinner; Form's <fieldset disabled> stays
          the double-submit guard. */}
      <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full">
        Log in
      </Button>
    </>
  );
}

// useSearchParams() opts the page out of static prerendering unless the
// component reading it is wrapped in Suspense (Next.js App Router
// requirement) — the fallback is never visible in practice since this
// value is available synchronously on the client.
export default function Login() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <LoginPage />
    </Suspense>
  );
}

function LoginPage() {
  const { mutateAsync } = useLogin();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [failure, setFailure] = useState<string | null>(null);
  const [mfaChallenge, setMfaChallenge] = useState<MfaChallengeState | null>(null);

  async function navigateAfterAuthentication() {
    // §1/§9 — the login/verify response itself is never trusted as the
    // ongoing auth source of truth; invalidate the canonical /me query so
    // AuthProvider derives authenticated state for real before
    // navigating, so the destination's ProtectedRoute (if any) doesn't
    // see stale anonymous data.
    //
    // Phase 5E — drop every user-scoped cache first. A session that expired
    // without an explicit logout leaves the previous user's orders/cart/
    // addresses cached in this tab; a different user signing in here must
    // never see them, even for one render.
    clearUserScopedQueries(queryClient);
    await queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
    const safePath = resolveReturnTo(searchParams.get("returnTo"));
    router.replace(safePath);
  }

  async function handleSubmit(values: LoginFormValues) {
    setFailure(null);
    try {
      const result: LoginResult = await mutateAsync(values);
      if (result.kind === "mfaChallenge") {
        // §2 row 5b — no session was established, no cookies were set.
        // challenge_id is held only in this component's state — never a
        // URL param, never localStorage/sessionStorage, never logged.
        setMfaChallenge({
          challengeId: result.data.challenge_id,
          deadline: Date.now() + result.data.expires_in_seconds * 1000,
        });
        return;
      }

      await navigateAfterAuthentication();
    } catch (error) {
      setFailure(failureMessage(error));
    }
  }

  if (mfaChallenge) {
    return (
      <MfaVerifyStep
        challenge={mfaChallenge}
        onVerified={() => {
          void navigateAfterAuthentication();
        }}
        onResetToLogin={(message) => {
          setMfaChallenge(null);
          setFailure(message);
        }}
      />
    );
  }

  // Batch 4: Stitch A1 auth card. No social login, no remember-me and no
  // status bar: none exist in the app. returnTo is still read only in
  // navigateAfterAuthentication above, unchanged.
  return (
    <AuthShell
      showBrand
      title="Log in"
      description="Welcome back. Enter your email and password to continue."
      footer={
        <>
          New to Bekaa3D?{" "}
          <Link href="/register" className={AUTH_INLINE_LINK_CLASSES}>
            Create an account
          </Link>
        </>
      }
    >
      {failure && <Alert variant="error" message={failure} />}
      <Form
        schema={loginSchema}
        defaultValues={{ email: "", password: "" }}
        onSubmit={handleSubmit}
        className="flex flex-col gap-5"
      >
        <LoginFields />
      </Form>
    </AuthShell>
  );
}
