import type { ApiError } from "@/lib/api/ApiError";

// bekaa3d-api-contract: branch on Problem.code, never on title/detail
// text — the backend's own copy is diagnostic and may change. One
// shared mapper for the error codes that mean the same safe thing
// everywhere across the admin area (settings/customers/reference-data/
// products/images); a caller with domain-specific copy needs (e.g. a
// field-level VALIDATION_ERROR mapped onto a specific form field) still
// branches on error.code itself first and only falls back to this for
// the generic case.
const GENERIC_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_MESSAGE = "We couldn't reach the server. Please try again.";
const TIMEOUT_MESSAGE = "The server took too long to respond. Please try again.";

const MESSAGES_BY_CODE: Record<string, string> = {
  NOT_FOUND: "This item could not be found. It may have been removed.",
  VERSION_CONFLICT: "This item was changed by someone else. Review the latest version and try again.",
  SLUG_CONFLICT: "That name or slug is already in use.",
  CATEGORY_IN_USE: "This is still used by a live product. Reassign it before archiving.",
  INVALID_STATE_TRANSITION: "This action can't be completed in the item's current state.",
  SETTING_INVALID: "Enter a valid value for this setting.",
  UPLOAD_REJECTED: "This file couldn't be uploaded. Use a JPEG, PNG or WebP image under 10 MB.",
  MALWARE_DETECTED: "This file was rejected by the security scan and was not uploaded.",
  SERVICE_UNAVAILABLE: "This service is temporarily unavailable. Please try again shortly.",
  RATE_LIMITED: "Too many requests. Please wait and try again.",
  VALIDATION_ERROR: "One or more fields are invalid.",
};

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value;
}

export function describeAdminError(error: unknown): string {
  if (!isApiError(error)) {
    return GENERIC_MESSAGE;
  }
  if (error.kind === "network") {
    return NETWORK_MESSAGE;
  }
  if (error.kind === "timeout") {
    return TIMEOUT_MESSAGE;
  }
  if (error.kind === "http" && error.code !== undefined) {
    return MESSAGES_BY_CODE[error.code] ?? GENERIC_MESSAGE;
  }
  return GENERIC_MESSAGE;
}
