"use client";

import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { GUEST_SUBMISSION_ERROR_COPY, type GuestSubmissionError } from "@/components/forms/guestSubmissionFeedback";

export interface ContactFormData {
  name: string;
  email: string;
  message: string;
}

export interface ContactFormProps {
  onSubmit: (data: ContactFormData) => void;
  isSubmitting?: boolean;
  error?: GuestSubmissionError | null;
  captchaSlot?: ReactNode;
}

// #FVS016-CONTACT-FORM
//
// Only the three VS-015-confirmed public fields exist: name, email,
// message (vertical-slice-plan.md's own Model-change line —
// `contact_messages`) — no phone/subject/company was invented. Reuses
// the shared `GUEST_SUBMISSION_ERROR_COPY` (see
// `#SHARED-GUEST-SUBMISSION-FEEDBACK`) so this form's captcha/rate-
// limit/generic guidance is identical to BYI's, by construction.
// `type="email"` is native browser semantics only — never treated as
// authoritative validation; the server remains the real authority.
//
// `captchaSlot` is a generic rendering seam for a future real
// CaptchaWidget — never a fake captcha built here (provider is
// NEEDS BACKEND CONFIRMATION, same open gap as FVS-015).
export function ContactForm({ onSubmit, isSubmitting = false, error = null, captchaSlot }: ContactFormProps) {
  const nameId = useId();
  const emailId = useId();
  const messageId = useId();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }
    onSubmit({ name, email, message });
  }

  const errorText = error ? GUEST_SUBMISSION_ERROR_COPY[error.kind] : null;

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label htmlFor={nameId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          Name
        </label>
        <input
          id={nameId}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
        />
      </div>

      <div className="mt-4">
        <label htmlFor={emailId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          Email
        </label>
        <input
          id={emailId}
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
        />
      </div>

      <div className="mt-4">
        <label htmlFor={messageId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          Message
        </label>
        <textarea
          id={messageId}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
        />
      </div>

      {captchaSlot && <div className="mt-4">{captchaSlot}</div>}

      {errorText && (
        <p role="alert" className="mt-4 text-caption text-danger">
          {errorText}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} isLoading={isSubmitting} className="mt-4">
        Send
      </Button>
    </form>
  );
}
