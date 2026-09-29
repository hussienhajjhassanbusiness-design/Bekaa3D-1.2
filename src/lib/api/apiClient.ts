import type { ApiError } from "./ApiError";
import { parseProblemBody } from "./problem";

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

// §13 point 1: apiClient calls only relative `/api/...` paths — never an
// absolute or cross-origin URL. This is the entire path contract; kept
// minimal per instruction, not a general-purpose URL framework.
function assertApiPath(path: string): void {
  if (!path.startsWith("/api/")) {
    throw new Error(`apiClient: path must start with "/api/", received "${path}"`);
  }
}

async function get<T = unknown>(path: string, options: ApiClientRequestOptions = {}): Promise<T> {
  assertApiPath(path);

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: { ok: boolean; status: number; text: () => Promise<string> };
  try {
    response = await fetch(path, { signal: controller.signal });
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
  throw apiError;
}

export const apiClient = { get };
