import type { ApiError } from "@/lib/api/ApiError";

// Current backend contract (docs/backend-handoff/openapi.json, backend
// 2dfb27b, ADR-025/026; backend src/app/api/captcha.py) for the three
// captcha-gated auth routes (register, resend-verification,
// password-reset/request) and the guest forms:
//   400 code CAPTCHA_INVALID   - token empty, invalid, expired or already used
//   503 code SERVICE_UNAVAILABLE + Retry-After: 30 - captcha could not be
//       verified, nothing was done (fails closed)
//   422 VALIDATION_ERROR loc ["body","captcha_token"] - token missing
// The UI branches on status + code only. The backend's detail/msg text is
// never shown.
export const CAPTCHA_INVALID_CODE = "CAPTCHA_INVALID";

export type CaptchaFailureKind = "invalid" | "unavailable" | "missing";

// Frontend-owned safe copy.
export const CAPTCHA_FAILURE_COPY: Record<CaptchaFailureKind, string> = {
  invalid: "The verification check expired or failed. Please complete it again and resubmit.",
  unavailable: "Verification is temporarily unavailable. Please try again in a moment.",
  missing: "Please complete the verification and try again.",
};

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

export function classifyCaptchaFailure(error: unknown): CaptchaFailureKind | null {
  if (!isApiError(error) || error.kind !== "http") {
    return null;
  }
  if (error.status === 400 && error.code === CAPTCHA_INVALID_CODE) {
    return "invalid";
  }
  // On these routes a 503 means "nothing was done, retry later" — whether
  // the captcha verifier or another dependency is down, the safe answer to
  // the user is the same.
  if (error.status === 503) {
    return "unavailable";
  }
  if (
    error.status === 422 &&
    error.errors?.some((item) => item.loc.length >= 2 && item.loc[0] === "body" && item.loc[1] === "captcha_token")
  ) {
    return "missing";
  }
  return null;
}

export function captchaFailureMessage(kind: CaptchaFailureKind): string {
  return CAPTCHA_FAILURE_COPY[kind];
}
