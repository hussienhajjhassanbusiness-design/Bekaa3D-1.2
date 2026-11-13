"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { RecoveryCodeList } from "@/components/auth/RecoveryCodeList";
import { useMfaRecoveryRegenerate } from "@/lib/auth/useMfaRecoveryRegenerate";
import { AuthCard } from "@/components/auth/AuthShell";

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

  // Batch 4 (DERIVED: A4 admin auth card styling inside AdminShell).
  // Markup only; the one-time reveal and acknowledgment are unchanged.
  if (codes) {
    return (
      <div className="flex justify-center py-6">
        <AuthCard
          width="wide"
          title="New recovery codes"
          status={{ icon: "check-circle", tone: "success" }}
          description="Your previous recovery codes no longer work. Save these new ones now."
        >
          <RecoveryCodeList codes={codes} />
          <label className="flex min-h-11 items-center gap-3 text-body-md text-on-surface">
            <input
              type="checkbox"
              className="h-5 w-5 shrink-0"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            I&rsquo;ve saved these codes somewhere safe
          </label>
          <Button size="lg" className="w-full" disabled={!acknowledged} onClick={() => router.replace("/admin/settings")}>
            Done
          </Button>
        </AuthCard>
      </div>
    );
  }

  return (
    <div className="flex justify-center py-6">
      <AuthCard
        title="Regenerate recovery codes"
        status={{ icon: "warning", tone: "warning" }}
        description="This replaces all of your existing recovery codes. The old codes will stop working immediately."
      >
        {failure && <Alert variant="error" message={failure} />}
        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <PasswordField
            label="Current password"
            autoComplete="current-password"
            leadingIcon="lock"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button type="submit" size="lg" className="w-full">
            Regenerate codes
          </Button>
        </form>
      </AuthCard>
    </div>
  );
}
