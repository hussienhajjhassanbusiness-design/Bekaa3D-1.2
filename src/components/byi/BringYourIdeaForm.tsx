"use client";

import { useId, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { precheckFiles, type UploadPrecheckRejection, type UploadValidationConfig } from "@/components/forms/uploadTypes";
import type { ByiErrorKind, ByiSubmissionError } from "./byiTypes";

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

// Frontend-owned safe copy for captcha/rate-limit guidance — matching
// vocabulary explicitly given as acceptable product copy
// (FVS-015-IMPLEMENTATION-PLAN.md §5/T01). "attachment" has no fixed
// copy here: only the backend-confirmed human-safe rejection field
// (error.message) is ever shown for it, never a client-invented
// generic.
const FIXED_ERROR_COPY: Partial<Record<ByiErrorKind, string>> = {
  captcha: "Please complete the verification and try again.",
  "rate-limit": "Please try again in a few minutes.",
  generic: "Something went wrong. Please try again.",
};

// #FVS015-BYI-FORM
//
// Only the two VS-014-confirmed public fields exist: description and
// attachments (vertical-slice-plan.md's own Model-change line —
// `custom_requests`/`custom_request_attachments`, no name/email/phone
// anywhere). Attachments reuse the EXISTING `precheckFiles` pure helper
// from FVS-012's uploadTypes.ts — not a second uploader. FVS-012's
// `FileUploader` component itself is deliberately NOT reused: its
// per-file immediate-upload-on-selection model doesn't match VS-014's
// confirmed single bundled multipart `CustomRequestCreate` request (see
// FVS-015-IMPLEMENTATION-PLAN.md §0's audit finding) — this form only
// collects `File` objects locally; nothing is uploaded until the
// (currently blocked) real submission adapter exists.
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
  const attachmentsId = useId();

  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [localRejections, setLocalRejections] = useState<readonly UploadPrecheckRejection[]>([]);
  const [announcement, setAnnouncement] = useState("");

  function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = "";
    if (files.length === 0) {
      return;
    }

    const { accepted, rejected } = precheckFiles(files, attachmentConfig, attachments.length);
    setLocalRejections(rejected);
    if (accepted.length > 0) {
      setAttachments((prev) => [...prev, ...accepted]);
      setAnnouncement(accepted.length === 1 ? `${accepted[0]!.name} added.` : `${accepted.length} files added.`);
    }
  }

  function handleRemove(index: number) {
    setAttachments((prev) => {
      const removed = prev[index];
      const next = prev.filter((_, i) => i !== index);
      if (removed) {
        setAnnouncement(`${removed.name} removed.`);
      }
      return next;
    });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }
    onSubmit({ description, attachments });
  }

  const errorText = error ? (error.kind === "attachment" ? error.message : FIXED_ERROR_COPY[error.kind]) : null;

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
        <label htmlFor={attachmentsId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          Attachments
        </label>
        <input id={attachmentsId} type="file" multiple onChange={handleFilesSelected} className="mt-1" />

        <div role="status" aria-live="polite" className="sr-only">
          {announcement}
        </div>

        {localRejections.map((rejection, index) => (
          <p key={index} role="alert" className="mt-2 text-caption text-danger">
            {rejection.reason}
          </p>
        ))}

        {attachments.length > 0 && (
          <ul className="mt-2">
            {attachments.map((file, index) => (
              <li key={index} className="flex items-center gap-2">
                <span className="text-body text-text-primary">{file.name}</span>
                <Button type="button" onClick={() => handleRemove(index)}>
                  Remove {file.name}
                </Button>
              </li>
            ))}
          </ul>
        )}
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
