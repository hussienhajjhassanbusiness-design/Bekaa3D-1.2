// FRONTEND-VERTICAL-SLICE-PLAN.md §13 "API Client Design" — canonical shape,
// transcribed verbatim. Do not add fields here without updating that plan
// section first (bekaa3d-api-contract: the server contract is the sole
// authority; this file must never get ahead of it).

export type ApiErrorKind = "http" | "network" | "timeout" | "parse";

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
  message: string;
  raw: unknown;
}
