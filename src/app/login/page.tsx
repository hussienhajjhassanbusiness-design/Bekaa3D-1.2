"use client";

import { Suspense, useState, type FormEvent } from "react";
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
import { resolveReturnTo } from "@/lib/auth/returnTo";

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
  const { remainingSeconds, isActive } = useCooldown(challenge.deadline);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
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
    }
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Log in</h1>
      {failure && <Alert variant="error" message={failure} />}
      <form onSubmit={handleSubmit} className="mt-4 max-w-[420px] mx-auto">
        {mode === "code" ? (
          <TextField
            label="Verification code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        ) : (
          <TextField
            label="Recovery code"
            autoComplete="off"
            value={recoveryCode}
            onChange={(event) => setRecoveryCode(event.target.value)}
          />
        )}
        <p className="mt-2 text-caption text-text-secondary" role="status">
          {isActive ? `Code expires in ${remainingSeconds} seconds.` : "This code has expired."}
        </p>
        <Button type="submit" className="mt-4 w-full">
          Verify
        </Button>
        <Button
          type="button"
          className="mt-2 w-full bg-transparent text-text-link"
          onClick={() => setMode((current) => (current === "code" ? "recovery" : "code"))}
        >
          {mode === "code" ? "Use a recovery code instead" : "Use my verification code instead"}
        </Button>
      </form>
    </>
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
    formState: { errors },
  } = useFormContext<LoginFormValues>();

  return (
    <>
      <TextField
        label="Email"
        type="text"
        inputMode="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register("email")}
      />
      <PasswordField
        label="Password"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register("password")}
      />
      <Button type="submit" className="mt-4 w-full">
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

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Log in</h1>
      {failure && <Alert variant="error" message={failure} />}
      <Form
        schema={loginSchema}
        defaultValues={{ email: "", password: "" }}
        onSubmit={handleSubmit}
        className="mt-4 max-w-[420px] mx-auto"
      >
        <LoginFields />
      </Form>
    </>
  );
}
