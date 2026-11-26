// FRONTEND-VERTICAL-SLICE-PLAN.md §13 "API Client Design" — canonical shape,
// transcribed verbatim. Do not add fields here without updating that plan
// section first (bekaa3d-api-contract: the server contract is the sole
// authority; this file must never get ahead of it).

// FVS-003 BATCH 3A Part C — "csrf" is a local precondition failure (the
// required csrf_token cookie was missing when apiClient.post was called
// with { csrf: true }), never a real server response. No request is sent
// in this case.
export type ApiErrorKind = "http" | "network" | "timeout" | "parse" | "csrf";

// Phase 2 auth/account batch — confirmed by docs/backend-handoff/openapi.json
// (components.schemas.ValidationError): every field-level validation failure
// the backend reports has exactly this shape. `loc` is Pydantic's own
// location path (e.g. ["body", "email"]); per the phase-2 contract note,
// callers drop loc[0] ("body"/"query"/"path") before mapping the remainder
// onto a form field — this type itself performs no such mapping, it only
// describes the confirmed wire shape.
export interface ValidationErrorItem {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

export interface ApiError {
  kind: ApiErrorKind;
  status?: number;
  type?: string;
  title?: string;
  detail?: string;
  instance?: string;
  // NEEDS BACKEND CONFIRMATION: correlation/request-ID header name — see
  // FRONTEND-VERTICAL-SLICE-PLAN.md §17. Never populate this until the
  // header name is confirmed by the backend.
  correlationId?: string;
  // FVS-002 BATCH 3 Part A — confirmed contract: 429 responses carry a
  // `Retry-After` header in whole seconds (FVS-002-IMPLEMENTATION-PLAN.md
  // §1 row 13). Only the parsed seconds value is exposed here — never a raw
  // Response/Headers object — and only when the header is present and a
  // valid finite non-negative whole number; otherwise this stays undefined
  // (never guessed). Populated for any non-2xx response that carries the
  // header, not just 429, since parsing is generic and status-agnostic.
  retryAfterSeconds?: number;
  // FVS-003 BATCH 3A Part B — confirmed contract: every backend failure mode
  // relevant to this slice (AUTH_REQUIRED, MFA_REQUIRED, CSRF_INVALID,
  // RATE_LIMITED) is identified by a top-level string `code` on the RFC 9457
  // problem body. Only a string value is ever accepted — never coerced,
  // never guessed from status alone. Production auth logic (Parts D/E/F)
  // must branch on `status`+`code`, never on `raw`.
  code?: string;
  // Phase 2 — confirmed by openapi.json's Problem schema (`errors` is a
  // required array on every Problem body, item shape = ValidationError).
  // Only ever populated with a real array of well-typed ValidationError
  // items (readOptionalValidationErrors in problem.ts) — a present-but-
  // wrong-shaped `errors` member (e.g. not an array, or an array of
  // non-ValidationError objects) is never coerced into this field; it
  // stays undefined, same as every other strictly-typed field here.
  errors?: ValidationErrorItem[];
  message: string;
  raw: unknown;
}
