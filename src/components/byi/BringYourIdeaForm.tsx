"use client";

import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { FileUploader } from "@/components/forms/FileUploader";
import type { UploadValidationConfig } from "@/components/forms/uploadTypes";
import { GUEST_SUBMISSION_ERROR_COPY } from "@/components/forms/guestSubmissionFeedback";
import type { ByiSubmissionError } from "./byiTypes";

export interface BringYourIdeaFormData {
  description: string;
  attachments: readonly File[];
}

export interface BringYourIdeaFormProps {
  onSubmit: (data: BringYourIdeaFormData) => void;
  isSubmitting?: boolean;
  error?: ByiSubmissionError | null;
  attachmentConfig?: UploadValidationConfig;
  captchaSlot?: ReactNode;
}

// #FVS015-BYI-FORM
//
// Only the two VS-014-confirmed public fields exist: description and
// attachments (vertical-slice-plan.md's own Model-change line —
// `custom_requests`/`custom_request_attachments`, no name/email/phone
// anywhere). Attachments reuse FVS-012's shared `FileUploader` in its
// deferred-selection mode (no `driver` prop) — the UPLOADER-REUSE
// FOLLOW-UP's resolution: the selection/precheck/list UX is
// transport-independent, so this form no longer duplicates it. Nothing
// is uploaded until the (currently blocked) real submission adapter
// exists; `onSelectionChange` is the only channel through which this
// form learns the current attachment list.
//
// `captchaSlot` is a generic rendering seam for a future real
// CaptchaWidget — never a fake captcha built here (provider is
// NEEDS BACKEND CONFIRMATION).
export function BringYourIdeaForm({
  onSubmit,
  isSubmitting = false,
  error = null,
  attachmentConfig = {},
  captchaSlot,
}: BringYourIdeaFormProps) {
  const descriptionId = useId();

  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<readonly File[]>([]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }
    onSubmit({ description, attachments });
  }

  const errorText = error ? (error.kind === "attachment" ? error.message : GUEST_SUBMISSION_ERROR_COPY[error.kind]) : null;

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label htmlFor={descriptionId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          Description
        </label>
        <textarea
          id={descriptionId}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="mt-1 w-full rounded-sm border border-border-default px-3 py-2 text-body text-text-primary"
        />
      </div>

      <div className="mt-4">
        <FileUploader label="Attachments" config={attachmentConfig} multiple onSelectionChange={setAttachments} />
      </div>

      {captchaSlot && <div className="mt-4">{captchaSlot}</div>}

      {errorText && (
        <p role="alert" className="mt-4 text-caption text-danger">
          {errorText}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} isLoading={isSubmitting} className="mt-4">
        Submit
      </Button>
    </form>
  );
}
