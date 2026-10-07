// #ARCHITECTURE-BYI-SUBMISSION-ADAPTER
//
// Frontend-normalized UI error categories ONLY — not a claim about any
// backend error code. VS-014 (vertical-slice-plan.md) never defines an
// error-code contract; these are the categories the product itself
// already requires distinct copy for (captcha failure, rate limiting,
// attachment rejection, everything else). A future submission adapter
// maps whatever the real backend response turns out to be onto one of
// these kinds — this file never guesses that mapping itself, and a
// component consuming `ByiSubmissionError` never infers a kind from
// message text.
export type ByiErrorKind = "captcha" | "rate-limit" | "attachment" | "generic";

export interface ByiSubmissionError {
  kind: ByiErrorKind;
  // Already-safe, human-readable text. For "attachment", this is the
  // one backend-confirmed human-safe rejection field once it exists —
  // never ApiError.raw, a full detail object, or scanner internals.
  message: string;
}
