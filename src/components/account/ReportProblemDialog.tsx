"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Alert } from "@/components/feedback/Alert";
import { DialogShell } from "@/components/feedback/DialogShell";
import { Button } from "@/components/forms/Button";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { PROBLEM_MESSAGE_MAX, problemMessageLength, validateProblemMessage } from "@/lib/orders/orderActions";

export interface ReportProblemDialogProps {
  open: boolean;
  pending: boolean;
  // A server failure (frontend-owned copy). The entered text is kept.
  error: string | null;
  onSubmit: (message: string) => void;
  onClose: () => void;
}

// #FVS031-REPORT-PROBLEM-DIALOG (phase 5G)
//
// The smallest form ProblemReportCreate needs: one `message` (1-5000
// characters, not blank). No category, subject or attachment — the
// contract has none. Validation mirrors the server's for fast feedback;
// the server's 422 is still mapped. The text survives a failed send and a
// close/reopen; the parent unmounts this dialog (clearing it) only after a
// confirmed success.
export function ReportProblemDialog({ open, pending, error, onSubmit, onClose }: ReportProblemDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const [message, setMessage] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  useEffect(() => {
    if (open) fieldRef.current?.focus();
  }, [open]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const problem = validateProblemMessage(message);
    setFieldError(problem);
    if (problem) {
      fieldRef.current?.focus();
      return;
    }
    onSubmit(message);
  }

  const length = problemMessageLength(message);

  return (
    <DialogShell open={open} onClose={onClose} isBusy={pending} labelledBy={titleId} describedBy={descriptionId}>
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <h2 id={titleId} className="font-headline text-headline-md text-on-surface">
            Report a problem
          </h2>
          <p id={descriptionId} className="mt-3 text-body-md text-on-surface-variant">
            Tell us what&apos;s wrong with the items you received. Our team will read your message and reply by email.
          </p>
        </div>
        <TextAreaField
          ref={fieldRef}
          label="What's the problem?"
          name="message"
          rows={5}
          value={message}
          onChange={(event) => {
            setMessage(event.target.value);
            if (fieldError) setFieldError(null);
          }}
          hint={`${length} / ${PROBLEM_MESSAGE_MAX} characters`}
          error={fieldError ?? undefined}
          disabled={pending}
        />
        {error && <Alert variant="error" message={error} />}
        <div className="flex flex-col-reverse gap-3 border-t border-outline-variant/30 pt-4 tablet:flex-row tablet:flex-wrap tablet:justify-end">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" isLoading={pending}>
            Send report
          </Button>
        </div>
      </form>
    </DialogShell>
  );
}
