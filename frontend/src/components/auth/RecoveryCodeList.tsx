"use client";

import { useState } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { Icon } from "@/components/ui/Icon";

export interface RecoveryCodeListProps {
  codes: readonly string[];
}

type CopyFeedback = "idle" | "success" | "error";

const COPY_SUCCESS_MESSAGE = "Codes copied to clipboard.";
const COPY_ERROR_MESSAGE = "Couldn't copy codes. Please select and copy them manually.";

/**
 * #FVS005-RECOVERY-CODES
 * #SECURITY-MFA-RECOVERY-CODES
 *
 * Recovery codes are credential material. This component is
 * presentation-only: it receives codes solely through props and performs
 * no fetching, no regeneration, and no persistence of any kind (no
 * localStorage/sessionStorage/cookie/IndexedDB/TanStack Query cache).
 * Clipboard/print actions run only in direct response to a user click.
 *
 * Future changes must not add browser-storage persistence, logging, or
 * any network call here — the parent flow owns the one-time reveal
 * lifecycle and the ephemeral handling of the real codes; this component
 * never extends that lifecycle on its own.
 */
export function RecoveryCodeList({ codes }: RecoveryCodeListProps) {
  const [copyFeedback, setCopyFeedback] = useState<CopyFeedback>("idle");

  if (codes.length === 0) {
    return null;
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setCopyFeedback("success");
    } catch {
      // Never render the raw clipboard exception — a safe, generic message
      // only (e.g. permission-denied details are browser-internal, not
      // user-actionable or safe to surface verbatim).
      setCopyFeedback("error");
    }
  }

  function handlePrint() {
    window.print();
  }

  // Batch 4: mono code grid in a tonal panel (2 columns from 640px), with
  // neutral outline actions. Presentation only.
  return (
    <div className="flex flex-col gap-4">
      <p className="text-body-md text-on-surface">
        Save these codes now — each is a one-time recovery credential, and they may not be shown again.
      </p>
      <ul className="grid list-none grid-cols-1 gap-x-6 gap-y-2 rounded-card border border-outline-variant/40 bg-surface-container-low p-4 sm:grid-cols-2">
        {codes.map((code) => (
          <li key={code} className="min-w-0">
            <code className="break-all font-label text-body-md text-on-surface">{code}</code>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={handleCopy}>
          <Icon name="content-copy" className="h-4 w-4" />
          Copy codes
        </Button>
        <Button variant="outline" onClick={handlePrint}>
          <Icon name="print" className="h-4 w-4" />
          Print codes
        </Button>
      </div>
      {copyFeedback === "success" && <Alert variant="success" message={COPY_SUCCESS_MESSAGE} />}
      {copyFeedback === "error" && <Alert variant="error" message={COPY_ERROR_MESSAGE} />}
    </div>
  );
}
