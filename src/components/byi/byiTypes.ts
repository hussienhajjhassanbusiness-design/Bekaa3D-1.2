import type { GuestSubmissionErrorKind } from "@/components/forms/guestSubmissionFeedback";

// #ARCHITECTURE-BYI-SUBMISSION-ADAPTER
//
// Frontend-normalized UI error categories ONLY — not a claim about any
// backend error code. VS-014 (vertical-slice-plan.md) never defines an
// error-code contract; these are the categories the product itself
// already requires distinct copy for. Extends the shared
// `GuestSubmissionErrorKind` (captcha/rate-limit/generic — see
// `#SHARED-GUEST-SUBMISSION-FEEDBACK`) with BYI's own extra
// "attachment" category, rather than duplicating the three shared
// kinds. A future submission adapter maps whatever the real backend
// response turns out to be onto one of these kinds — this file never
// guesses that mapping itself, and a component consuming
// `ByiSubmissionError` never infers a kind from message text.
export type ByiErrorKind = GuestSubmissionErrorKind | "attachment";

export interface ByiSubmissionError {
  kind: ByiErrorKind;
  // Already-safe, human-readable text. For "attachment", this is the
  // one backend-confirmed human-safe rejection field once it exists —
  // never ApiError.raw, a full detail object, or scanner internals.
  message: string;
}
