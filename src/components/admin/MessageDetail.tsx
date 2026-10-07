"use client";

import { Button } from "@/components/forms/Button";
import { StatusBadge } from "./StatusBadge";
import {
  getNextContactMessageAction,
  describeContactMessageStatus,
  type ContactMessageStatus,
} from "@/lib/admin/contactMessageWorkflow";

// Frontend-normalized detail model — only the VS-015-confirmed public
// fields plus the normalized status (FVS-017-IMPLEMENTATION-PLAN.md
// §1). No IP/user-agent/captcha-score/internal-notes/database-metadata/
// moderation-flags — none of that is a confirmed admin-endpoint field
// (#SECURITY-CONTACT-PII).
export interface MessageDetailModel {
  name: string;
  email: string;
  message: string;
  status: ContactMessageStatus;
}

export interface MessageDetailProps {
  message: MessageDetailModel;
  onTransition: (nextStatus: ContactMessageStatus) => void;
  isPending?: boolean;
  error?: string | null;
}

// #FVS017-MESSAGE-DETAIL
//
// Only the single legal next action (per
// `getNextContactMessageAction`) ever renders — no status dropdown, no
// free-text field, no arbitrary transition selector. Message text is
// rendered as plain text with CSS `whiteSpace: pre-wrap` to preserve
// line breaks safely — never `dangerouslySetInnerHTML`.
export function MessageDetail({ message, onTransition, isPending = false, error = null }: MessageDetailProps) {
  const action = getNextContactMessageAction(message.status);
  const { label, tone } = describeContactMessageStatus(message.status);

  return (
    <div>
      <p className="text-h3 font-bold text-text-primary">{message.name}</p>
      <a href={`mailto:${message.email}`} className="text-body text-brand-dark-green underline">
        {message.email}
      </a>
      <div className="mt-2">
        <StatusBadge label={label} tone={tone} />
      </div>
      <p className="mt-4 text-body text-text-primary" style={{ whiteSpace: "pre-wrap" }}>
        {message.message}
      </p>

      {error && (
        <p role="alert" className="mt-4 text-caption text-danger">
          {error}
        </p>
      )}

      {action && (
        <Button type="button" onClick={() => onTransition(action.nextStatus)} disabled={isPending} isLoading={isPending} className="mt-4">
          {action.label}
        </Button>
      )}
    </div>
  );
}
