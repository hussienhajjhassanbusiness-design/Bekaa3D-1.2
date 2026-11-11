import type { ApiError } from "@/lib/api/ApiError";
import { captchaFailureMessage, classifyCaptchaFailure } from "@/lib/captcha/captchaErrors";

// #SHARED-GUEST-SUBMISSION-ERRORS (phase 6B)
//
// One mapper for the public, captcha-gated guest forms: Contact
// (POST /api/v1/contact-messages) and Bring Your Idea
// (POST /api/v1/custom-requests). Current backend contract (backend 2dfb27b,
// engagement/api/contact_messages.py + custom_requests.py, api/captcha.py):
//   400 CAPTCHA_INVALID                      - token refused / expired / used
//   422 VALIDATION_ERROR loc [body, <field>] - a field is missing or invalid
//   429 RATE_LIMITED (+ Retry-After)         - per-IP / per-email hourly limit
//   503 SERVICE_UNAVAILABLE                  - captcha (or, for BYI, the
//                                              malware scanner) unavailable
// The UI branches on status + code + loc only. Problem.detail, title and the
// validation `msg` text are never shown.

export interface GuestSubmissionFailure {
  message: string;
  // Backend field names a 422 flagged (loc[1]); empty for other failures.
  fields: string[];
}

export const GUEST_SUBMISSION_COPY = {
  generic: "Something went wrong. Please try again.",
  network: "We couldn't reach the server. Please check your connection and try again.",
  timeout: "The server took too long to respond. Please try again.",
  rateLimited: "Too many submissions. Please try again later.",
  rateLimitedWithWait: (seconds: number) => {
    const minutes = Math.ceil(seconds / 60);
    return minutes > 1
      ? `Too many submissions. Please try again in about ${minutes} minutes.`
      : "Too many submissions. Please try again in a minute.";
  },
  invalidFields: (labels: string[]) => `Please check: ${labels.join(", ")}.`,
  invalid: "Some details couldn't be accepted. Please check the form and try again.",
} as const;

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

function flaggedFields(error: ApiError): string[] {
  const names = (error.errors ?? [])
    .map((item) => item.loc[1])
    .filter((name): name is string => typeof name === "string");
  return [...new Set(names)];
}

export function describeGuestSubmissionFailure(
  error: unknown,
  fieldLabels: Readonly<Record<string, string>>
): GuestSubmissionFailure {
  const captcha = classifyCaptchaFailure(error);
  if (captcha) {
    return { message: captchaFailureMessage(captcha), fields: [] };
  }
  if (!isApiError(error)) {
    return { message: GUEST_SUBMISSION_COPY.generic, fields: [] };
  }
  if (error.kind === "network") return { message: GUEST_SUBMISSION_COPY.network, fields: [] };
  if (error.kind === "timeout") return { message: GUEST_SUBMISSION_COPY.timeout, fields: [] };
  if (error.kind !== "http") return { message: GUEST_SUBMISSION_COPY.generic, fields: [] };

  if (error.status === 429) {
    return {
      message:
        error.retryAfterSeconds !== undefined
          ? GUEST_SUBMISSION_COPY.rateLimitedWithWait(error.retryAfterSeconds)
          : GUEST_SUBMISSION_COPY.rateLimited,
      fields: [],
    };
  }
  if (error.status === 422) {
    const fields = flaggedFields(error).filter((name) => name in fieldLabels);
    if (fields.length > 0) {
      return { message: GUEST_SUBMISSION_COPY.invalidFields(fields.map((f) => fieldLabels[f]!)), fields };
    }
    return { message: GUEST_SUBMISSION_COPY.invalid, fields: [] };
  }
  return { message: GUEST_SUBMISSION_COPY.generic, fields: [] };
}
