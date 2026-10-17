"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { RecoveryCodeList } from "@/components/auth/RecoveryCodeList";
import { useMfaRecoveryRegenerate } from "@/lib/auth/useMfaRecoveryRegenerate";

// P1-2 (POST /api/v1/auth/mfa/recovery-codes/regenerate) — invalidates
// every existing recovery code and issues ten new ones, shown exactly
// once. Requires the current password as a step-up confirmation before
// a destructive, irreversible credential rotation. No "disable MFA"
// path exists anywhere in the backend contract; this page only ever
// regenerates codes for an already-enrolled administrator.
const INVALID_CREDENTIALS_MESSAGE = "That password is incorrect. Please try again.";
const GENERIC_FAILURE_MESSAGE = "Something went wrong. Please try again.";

function isInvalidCredentials(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as { kind: unknown }).kind === "http" &&
    (error as { status?: unknown }).status === 401 &&
    (error as { code?: unknown }).code === "INVALID_CREDENTIALS"
  );
}

export default function MfaRecoveryCodesPage() {
  const router = useRouter();
  const { mutateAsync } = useMfaRecoveryRegenerate();
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<readonly string[] | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      const result = await mutateAsync({ current_password: password });
      setCodes(result.recovery_codes);
    } catch (error) {
      setFailure(isInvalidCredentials(error) ? INVALID_CREDENTIALS_MESSAGE : GENERIC_FAILURE_MESSAGE);
    }
  }

  if (codes) {
    return (
      <>
        <h1 className="text-h1 font-bold text-text-primary">New recovery codes</h1>
        <p className="mt-2 text-body text-text-secondary">
          Your previous recovery codes no longer work. Save these new ones now.
        </p>
        <div className="mt-4">
          <RecoveryCodeList codes={codes} />
        </div>
        <label className="mt-4 flex items-center gap-2 text-body text-text-primary">
          <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
          I&rsquo;ve saved these codes somewhere safe
        </label>
        <Button className="mt-4 w-full" disabled={!acknowledged} onClick={() => router.replace("/admin/settings")}>
          Done
        </Button>
      </>
    );
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Regenerate recovery codes</h1>
      <p className="mt-2 text-body text-text-secondary">
        This replaces all of your existing recovery codes. The old codes will stop working immediately.
      </p>
      {failure && <Alert variant="error" message={failure} />}
      <form onSubmit={handleSubmit} className="mt-4 max-w-[420px]">
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <Button type="submit" className="mt-4 w-full">
          Regenerate codes
        </Button>
      </form>
    </>
  );
}
