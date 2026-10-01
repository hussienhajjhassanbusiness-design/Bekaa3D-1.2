import type { ApiError } from "./ApiError";
import { parseProblemBody } from "./problem";
import { readCsrfToken, CSRF_HEADER_NAME } from "@/lib/auth/csrf";

// FRONTEND-VERTICAL-SLICE-PLAN.md §13, point 2: "a frontend-only operational
// default, not a backend contract — proposed 10s for the health check
// specifically, overridable per call." This is the client's own default,
// overridable per call via ApiClientRequestOptions.timeoutMs.
const DEFAULT_TIMEOUT_MS = 10_000;

// Small, status-code-keyed fallback table (§13 point 9). Deliberately NOT
// the raw backend `detail`/`raw` text — that field's safety for end-user
// display is unconfirmed. The 5xx and network strings are the plan's own
// examples, used verbatim; the 4xx and timeout strings are this task's own
// minimal, safe extrapolation (the plan gives no exact string for either).
const MESSAGE_SERVER_ERROR = "Something went wrong. Please try again.";
const MESSAGE_CLIENT_ERROR = "There was a problem with your request. Please try again.";
const MESSAGE_NETWORK = "We couldn't reach the server.";
const MESSAGE_TIMEOUT = "The server took too long to respond. Please try again.";

export interface ApiClientRequestOptions {
  timeoutMs?: number;
  // FVS-003 BATCH 3A Part C — explicit opt-in only (confirmed contract:
  // required for refresh/logout/every authenticated write; NOT required
  // for login or FVS-002's anonymous POSTs). Never a blanket auto-attach —
  // callers that don't need it simply never pass this.
  csrf?: boolean;
}

function fallbackHttpMessage(status: number): string {
  return status >= 500 ? MESSAGE_SERVER_ERROR : MESSAGE_CLIENT_ERROR;
}

function networkError(): ApiError {
  return { kind: "network", message: MESSAGE_NETWORK, raw: undefined };
}

function timeoutError(): ApiError {
  return { kind: "timeout", message: MESSAGE_TIMEOUT, raw: undefined };
}

const MESSAGE_CSRF = "Unable to verify your session. Please refresh the page and try again.";

// FVS-003 BATCH 3A Part C — a missing CSRF cookie when one was explicitly
// required is a local precondition failure, not a server response: no
// request is ever sent, and no fake token is ever invented.
function missingCsrfError(): ApiError {
  return { kind: "csrf", message: MESSAGE_CSRF, raw: undefined };
}

// FVS-002 BATCH 3 Part A (FVS-002-IMPLEMENTATION-PLAN.md §1 row 13) — parses
// only a valid finite non-negative whole-seconds Retry-After value. Anything
// else (missing header, non-numeric, negative, fractional) resolves
// undefined rather than guessed — this deliberately does not implement the
// HTTP-date form of Retry-After, since the confirmed contract states whole
// seconds only.
const WHOLE_SECONDS_PATTERN = /^[0-9]+$/;

function parseRetryAfterSeconds(headers: { get(name: string): string | null } | undefined): number | undefined {
  const raw = headers?.get("Retry-After");
  if (raw === null || raw === undefined) {
    return undefined;
  }
  const trimmed = raw.trim();
  if (!WHOLE_SECONDS_PATTERN.test(trimmed)) {
    return undefined;
  }
  return Number(trimmed);
}

// §13 point 1: apiClient calls only relative `/api/...` paths — never an
// absolute or cross-origin URL. This is the entire path contract; kept
// minimal per instruction, not a general-purpose URL framework.
function assertApiPath(path: string): void {
  if (!path.startsWith("/api/")) {
    throw new Error(`apiClient: path must start with "/api/", received "${path}"`);
  }
}

// FVS002-T06 — the shared transport core behind both get() and post():
// same path assertion, same AbortController-driven timeout, same success
// contract (2xx + empty/unparseable body resolves undefined, never an
// ApiError), same failure contract (delegates to T08's single
// parseProblemBody — never duplicated). get()/post() differ only in what
// RequestInit they pass in; this function's own behavior is otherwise
// untouched from FVS001-T09's original get()-only implementation.
async function request<T>(path: string, init: RequestInit, timeoutMs: number): Promise<T> {
  assertApiPath(path);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: {
    ok: boolean;
    status: number;
    text: () => Promise<string>;
    headers?: { get(name: string): string | null };
  };
  try {
    response = await fetch(path, { ...init, signal: controller.signal });
  } catch {
    // §13 point 5: an aborted request (our own timeout) vs. point 4: any
    // other rejection (offline, DNS failure, connection refused, etc.) —
    // distinguished by whether OUR controller is the one that aborted,
    // since no external caller-provided AbortSignal exists in this API.
    throw controller.signal.aborted ? timeoutError() : networkError();
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();

  if (response.ok) {
    // §13 point 6: a 2xx response is never turned into an error solely
    // because its body is empty or unparseable — that's still success,
    // resolving to `undefined`.
    if (text === "") {
      return undefined as T;
    }
    try {
      return JSON.parse(text) as T;
    } catch {
      return undefined as T;
    }
  }

  // §13 point 7: delegate all non-2xx body normalization to T08's single
  // Problem parser — never duplicate RFC 9457 parsing logic here. Per the
  // approved ApiError.kind clarification, a malformed non-2xx body stays
  // kind: "parse" (T08's own behavior is not overridden). The real HTTP
  // `status` is attached only for kind "http", matching ApiError's own
  // "status?: number; // present for kind: 'http'" contract — a kind:
  // "parse" result never got a status from T08 either.
  const parsed = parseProblemBody(text);
  const apiError: ApiError = { ...parsed, message: fallbackHttpMessage(response.status) };
  if (apiError.kind === "http") {
    apiError.status = response.status;
  }
  const retryAfterSeconds = parseRetryAfterSeconds(response.headers);
  if (retryAfterSeconds !== undefined) {
    apiError.retryAfterSeconds = retryAfterSeconds;
  }
  throw apiError;
}

async function get<T = unknown>(path: string, options: ApiClientRequestOptions = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return request<T>(path, {}, timeoutMs);
}

// FVS002-T06 — JSON write support, reusing every rule request() already
// enforces. Content-Type is set only when a body is actually sent (no
// unnecessary header on a bodyless POST). No retry, no auth/CSRF header, no
// credentials-mode change, no interceptor system — transport only. Callers
// pass a full /api/... path; this task does not call any auth endpoint
// itself (that remains contract-gated, FVS-002-IMPLEMENTATION-PLAN.md §1).
async function post<T = unknown>(
  path: string,
  body?: unknown,
  options: ApiClientRequestOptions = {}
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.csrf) {
    // Read fresh at send time, every time — never cached across requests
    // (§5 of the plan: the token happens to stay stable across a refresh,
    // but nothing here depends on that stability to be correct).
    const csrfToken = readCsrfToken();
    if (csrfToken === undefined) {
      throw missingCsrfError();
    }
    headers[CSRF_HEADER_NAME] = csrfToken;
  }

  const hasHeaders = Object.keys(headers).length > 0;
  const init: RequestInit = {
    method: "POST",
    ...(hasHeaders ? { headers } : {}),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
  return request<T>(path, init, timeoutMs);
}

export const apiClient = { get, post };
