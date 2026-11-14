import type { ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";

export interface SuccessReceiptProps {
  message: string;
  // Optional short heading (Batch 8, COMPONENT-SPECS §48 "Request Received").
  title?: string;
  // Optional follow-up controls (e.g. "Send another message"), rendered
  // under the message, outside the announced status text.
  actions?: ReactNode;
}

// #SHARED-SUCCESS-RECEIPT
//
// Generalized from FVS-015's own BYI-only component: generic, safe
// confirmation for any guest-submission flow (BYI, Contact, future
// ones). `message` is required — no default is baked in here, since a
// default would inevitably be flavored toward one caller's domain (the
// original BYI version's default said "idea", which would have been
// wrong for Contact). No internal database id, storage key, attachment
// URL, captcha proof, or internal status is ever exposed — none of
// that is a backend-confirmed public-safe field for any consumer yet.
//
// Redesign Batch 8: the Stitch §48 result card (centred, verified glyph in a
// lime circle, primary heading). Still one `role="status"` region holding
// the title and message.
export function SuccessReceipt({ message, title, actions }: SuccessReceiptProps) {
  return (
    <div className="flex flex-col items-center rounded-card border border-primary/20 bg-surface-container-lowest px-6 py-10 text-center tablet:px-10">
      <span className="flex h-20 w-20 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
        <Icon name="verified" className="h-10 w-10" />
      </span>
      <div role="status" className="mt-6 max-w-md">
        {title && <p className="font-headline text-headline-md text-primary tablet:text-headline-lg">{title}</p>}
        <p className={`font-body text-body-md text-on-surface-variant ${title ? "mt-2" : ""}`}>{message}</p>
      </div>
      {actions && (
        <div className="mt-8 flex w-full flex-col justify-center gap-3 tablet:w-auto tablet:flex-row">{actions}</div>
      )}
    </div>
  );
}
