import type { ApiError } from "./ApiError";

// Generic fallback UI copy. Deliberately never the raw `detail` text verbatim
// — presenting server-authored prose as UI copy is a later, status-aware
// concern (out of scope for T08's pure parsing responsibility).
const GENERIC_MESSAGE = "An unexpected error occurred.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readOptionalString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === "string" ? value : undefined;
}

function readOptionalNumber(record: Record<string, unknown>, key: string): number | undefined {
  const value = record[key];
  return typeof value === "number" ? value : undefined;
}

// Parses an HTTP response body as an RFC 9457 Problem Details object,
// recognizing ONLY the five confirmed fields (FRONTEND-VERTICAL-SLICE-
// PLAN.md §14: type/title/status/detail/instance). Any other member —
// including a future `errors[]` validation extension, which is explicitly
// NEEDS BACKEND CONFIRMATION — is preserved unmodified inside `raw` and is
// never given a typed accessor here (bekaa3d-api-contract: never invent an
// unconfirmed field).
export function parseProblemBody(rawText: string): ApiError {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    return {
      kind: "parse",
      message: GENERIC_MESSAGE,
      raw: rawText,
    };
  }

  if (!isRecord(parsed)) {
    return {
      kind: "http",
      message: GENERIC_MESSAGE,
      raw: parsed,
    };
  }

  return {
    kind: "http",
    type: readOptionalString(parsed, "type"),
    title: readOptionalString(parsed, "title"),
    status: readOptionalNumber(parsed, "status"),
    detail: readOptionalString(parsed, "detail"),
    instance: readOptionalString(parsed, "instance"),
    // FVS-003 BATCH 3A Part B — the one additional top-level field this
    // slice's confirmed contract actually needs (AUTH_REQUIRED/MFA_REQUIRED/
    // CSRF_INVALID/RATE_LIMITED) — parsed with the same only-if-a-real-
    // string rule as every other field here, never coerced.
    code: readOptionalString(parsed, "code"),
    message: GENERIC_MESSAGE,
    raw: parsed,
  };
}
