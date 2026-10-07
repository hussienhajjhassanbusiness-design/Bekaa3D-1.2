// #SHARED-GUEST-SUBMISSION-FEEDBACK
//
// One consistent captcha/rate-limit/generic vocabulary shared by every
// unauthenticated public-submission form (BYI — FVS-015; Contact —
// FVS-016; any future one) — a visitor should learn this interaction
// once rather than meet slightly different copy per form. A form with
// its own extra, domain-specific error category (e.g. BYI's
// "attachment") extends this union rather than duplicating the three
// shared kinds (see byiTypes.ts's `ByiErrorKind`).
//
// These are UI categories only, never a backend error-code claim — a
// future adapter maps whatever the real backend response turns out to
// be onto one of these kinds.
export type GuestSubmissionErrorKind = "captcha" | "rate-limit" | "generic";

export interface GuestSubmissionError {
  kind: GuestSubmissionErrorKind;
  message: string;
}

// Frontend-owned safe copy — explicitly supplied as acceptable product
// copy by the governing task for both BYI and Contact; not a backend
// contract item, so every consumer sharing this constant stays
// consistent automatically if the copy is ever revised.
export const GUEST_SUBMISSION_ERROR_COPY: Record<GuestSubmissionErrorKind, string> = {
  captcha: "Please complete the verification and try again.",
  "rate-limit": "Please try again in a few minutes.",
  generic: "Something went wrong. Please try again.",
};
