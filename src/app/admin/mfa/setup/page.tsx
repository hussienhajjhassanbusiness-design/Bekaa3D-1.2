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

  if (step.kind === "password") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Set up two-factor authentication</h1>
        {failure && <Alert variant="error" message={failure} />}
        <form onSubmit={handleBeginSetup} className="mt-4 max-w-[420px]">
          <PasswordField
            label="Current password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button type="submit" className="mt-4 w-full">
            Begin setup
          </Button>
        </form>
      </>
    );
  }

  if (step.kind === "code") {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">Set up two-factor authentication</h1>
        {failure && <Alert variant="error" message={failure} />}
        <p className="mt-4 text-body text-text-primary">
          Scan this QR code with your authenticator app, or enter the secret manually:
        </p>
        <p className="mt-2 break-all text-body font-mono text-text-primary">{step.setup.secret}</p>
        <p className="mt-2 break-all text-caption text-text-secondary">
          {redactOtpauthSecret(step.setup.otpauth_uri, step.setup.secret)}
        </p>
        <form onSubmit={handleConfirm} className="mt-4 max-w-[420px]">
          <TextField
            label="Verification code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
          <Button type="submit" className="mt-4 w-full">
            Confirm
          </Button>
        </form>
      </>
    );
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Save your recovery codes</h1>
      <RecoveryCodeList codes={step.codes} />
      <label className="mt-4 flex items-center gap-2 text-body text-text-primary">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
        />
        I&rsquo;ve saved these codes somewhere safe
      </label>
      <Button className="mt-4 w-full" disabled={!acknowledged} onClick={() => router.replace("/admin")}>
        Continue
      </Button>
    </>
  );
}
