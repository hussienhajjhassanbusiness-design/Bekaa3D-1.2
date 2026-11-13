"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { RecoveryCodeList } from "@/components/auth/RecoveryCodeList";
import { useMfaSetup, type MfaSetupResponse } from "@/lib/auth/useMfaSetup";
import { useMfaSetupConfirm } from "@/lib/auth/useMfaSetupConfirm";
import { AuthCard } from "@/components/auth/AuthShell";

// Phase 3 (FVS-005/P1-2) — MFA enrolment for an administrator whose
// enrolment is incomplete. Reached either directly or via AdminGuard's
// mfaRequiredSignal redirect (src/components/admin/AdminGuard.tsx).
//
// `secret`/`otpauth_uri` (step 1 -> 2) are sensitive and held only in this
// component's own React state — never logged, never persisted to any
// storage, and never rendered again once the admin moves past step 2.
// Recovery codes (step 3) are shown exactly once and require an explicit
// "I've saved these" acknowledgment before the admin can leave the page —
// there is no way to see them again afterward (no "disable MFA" or
// re-reveal endpoint exists).
type Step =
  | { kind: "password" }
  | { kind: "code"; setup: MfaSetupResponse }
  | { kind: "recoveryCodes"; codes: readonly string[] };

const INVALID_CREDENTIALS_MESSAGE = "That password is incorrect. Please try again.";
const ALREADY_ENABLED_MESSAGE = "Two-factor authentication is already set up for this account.";
const MFA_INVALID_MESSAGE = "That code didn't match. Please try again.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";

// The otpauth URI embeds the raw secret as its `secret=` query value by
// construction (it's the same credential, just URI-encoded for a QR/
// authenticator-app deep link). Redacting it here keeps the manual-entry
// secret above as the only place that value is shown as plain text —
// avoids duplicating sensitive text across two elements for no UX benefit.
function redactOtpauthSecret(otpauthUri: string, secret: string): string {
  return otpauthUri.replace(secret, "••••••••");
}

function isHttpError(error: unknown, status: number, code: string): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as { kind: unknown }).kind === "http" &&
    (error as { status?: unknown }).status === status &&
    (error as { code?: unknown }).code === code
  );
}

export default function MfaSetupPage() {
  const router = useRouter();
  const { mutateAsync: beginSetup } = useMfaSetup();
  const { mutateAsync: confirmSetup } = useMfaSetupConfirm();

  const [step, setStep] = useState<Step>({ kind: "password" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function handleBeginSetup(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      const setup = await beginSetup({ current_password: password });
      setStep({ kind: "code", setup });
    } catch (error) {
      if (isHttpError(error, 401, "INVALID_CREDENTIALS")) {
        setFailure(INVALID_CREDENTIALS_MESSAGE);
      } else if (isHttpError(error, 409, "INVALID_STATE_TRANSITION")) {
        setFailure(ALREADY_ENABLED_MESSAGE);
      } else {
        setFailure(GENERIC_FAILURE_MESSAGE);
      }
    }
  }

  async function handleConfirm(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      const result = await confirmSetup({ code });
      setStep({ kind: "recoveryCodes", codes: result.recovery_codes });
    } catch (error) {
      setFailure(isHttpError(error, 422, "MFA_INVALID") ? MFA_INVALID_MESSAGE : GENERIC_FAILURE_MESSAGE);
    }
  }

  // Batch 4 (DERIVED: A4 admin auth card styling, rendered inside
  // AdminShell, so the card only, no canvas). Markup only: the secret is
  // still shown once in step 2 and never again, the otpauth URI is still
  // redacted, and recovery codes still need the acknowledgment. The
  // shell itself is Batch 9.
  if (step.kind === "password") {
    return (
      <div className="flex justify-center py-6">
        <AuthCard
          eyebrow="Step 1 of 3"
          title="Set up two-factor authentication"
          status={{ icon: "lock", tone: "info" }}
          description="Confirm your current password to start. Administrator accounts need two-factor authentication."
        >
          {failure && <Alert variant="error" message={failure} />}
          <form onSubmit={handleBeginSetup} className="flex flex-col gap-6">
            <PasswordField
              label="Current password"
              autoComplete="current-password"
              leadingIcon="lock"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" size="lg" className="w-full">
              Begin setup
            </Button>
          </form>
        </AuthCard>
      </div>
    );
  }

  if (step.kind === "code") {
    return (
      <div className="flex justify-center py-6">
        <AuthCard
          width="wide"
          eyebrow="Step 2 of 3"
          title="Set up two-factor authentication"
          status={{ icon: "lock", tone: "info" }}
        >
          {failure && <Alert variant="error" message={failure} />}
          <div className="flex flex-col gap-3">
            <p className="text-body-md text-on-surface">
              Scan this QR code with your authenticator app, or enter the secret manually:
            </p>
            <div className="rounded-card border border-outline-variant/40 bg-surface-container-low p-4">
              <p className="font-label text-label-caps uppercase text-on-surface-variant">Setup key</p>
              <p className="mt-2 break-all font-label text-body-md text-on-surface">{step.setup.secret}</p>
            </div>
            <p className="break-all text-caption text-on-surface-variant">
              {redactOtpauthSecret(step.setup.otpauth_uri, step.setup.secret)}
            </p>
          </div>
          <form onSubmit={handleConfirm} className="flex flex-col gap-6">
            <TextField
              label="Verification code"
              inputMode="numeric"
              autoComplete="one-time-code"
              mono
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <Button type="submit" size="lg" className="w-full">
              Confirm
            </Button>
          </form>
        </AuthCard>
      </div>
    );
  }

  return (
    <div className="flex justify-center py-6">
      <AuthCard
        width="wide"
        eyebrow="Step 3 of 3"
        title="Save your recovery codes"
        status={{ icon: "check-circle", tone: "success" }}
      >
        <RecoveryCodeList codes={step.codes} />
        <label className="flex min-h-11 items-center gap-3 text-body-md text-on-surface">
          <input
            type="checkbox"
            className="h-5 w-5 shrink-0"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          I&rsquo;ve saved these codes somewhere safe
        </label>
        <Button size="lg" className="w-full" disabled={!acknowledged} onClick={() => router.replace("/admin")}>
          Continue
        </Button>
      </AuthCard>
    </div>
  );
}
