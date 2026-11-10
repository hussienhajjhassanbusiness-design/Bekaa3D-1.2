import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "./apiClient";

// FVS001-T09 — built exactly to FVS-001-IMPLEMENTATION-PLAN.md §13's eleven
// numbered responsibilities, consuming FVS001-T08's parseProblemBody. Every
// fetch call in this file is stubbed via vi.stubGlobal("fetch", ...) — no
// real network request is ever made, and stub/mock/timer state never leaks
// between tests (see afterEach below).
//
// Case I (an external, caller-provided AbortSignal) is deliberately NOT
// tested here: §13's only quoted public-API usage is `apiClient.get(path)`
// with no external-signal parameter, so adding or testing one would be
// inventing a contract the plan doesn't specify.

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

function textResponse(status: number, text: string) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
  };
}

// FVS-002 BATCH 3 Part A — a response carrying real headers, used only by
// the Retry-After tests below. Uses the real Headers class so `.get()`'s
// case-insensitivity matches actual fetch() behavior, not a hand-rolled
// stand-in.
function jsonResponseWithHeaders(status: number, body: unknown, headers: Record<string, string>) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
    headers: new Headers(headers),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("apiClient.get", () => {
  describe("A. Successful JSON response", () => {
    it("returns the parsed JSON body directly, with no ApiError wrapper, calling fetch once against the given relative path", async () => {
      const fetchStub = vi.fn().mockResolvedValue(jsonResponse(200, { ready: true }));
      vi.stubGlobal("fetch", fetchStub);

      const result = await apiClient.get("/api/health/ready");

      expect(result).toEqual({ ready: true });
      expect(fetchStub).toHaveBeenCalledTimes(1);
      expect(fetchStub.mock.calls[0]?.[0]).toBe("/api/health/ready");
    });
  });

  describe("B. Successful empty body", () => {
    it("resolves to undefined on a 2xx response with an empty body, without throwing an ApiError", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(200, "")));

      const result = await apiClient.get("/api/health/live");

      expect(result).toBeUndefined();
    });
  });

  describe("C. Successful non-JSON / unparseable body", () => {
    it("resolves to undefined on a 2xx response whose body is not valid JSON, treating it as success, not kind: 'parse'", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(200, "not valid json {{{")));

      const result = await apiClient.get("/api/health/live");

      expect(result).toBeUndefined();
    });
  });

  describe("D. RFC 9457 HTTP error", () => {
    it("throws an ApiError with kind 'http', the confirmed RFC fields, the real HTTP status, and no invented fields", async () => {
      const problemBody = {
        type: "https://example.com/probs/not-ready",
        title: "Not Ready",
        status: 503,
        detail: "Database unavailable",
        instance: "/api/health/ready",
      };
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, problemBody)));

      await expect(apiClient.get("/api/health/ready")).rejects.toMatchObject({
        kind: "http",
        status: 503,
        type: "https://example.com/probs/not-ready",
        title: "Not Ready",
        detail: "Database unavailable",
        instance: "/api/health/ready",
      });
    });

    it("never populates correlationId, and leaves errors undefined when the response carries none", async () => {
      const problemBody = { type: "https://example.com/probs/not-ready", title: "Not Ready", status: 503 };
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, problemBody)));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { correlationId?: string }).correlationId).toBeUndefined();
      // Phase 2 — errors[] is now a confirmed field (openapi.json Problem
      // schema); a response that carries none still resolves it to
      // undefined, never a fabricated empty/default array.
      expect((caught as { errors?: unknown }).errors).toBeUndefined();
    });
  });

  describe("E. Valid non-problem JSON error", () => {
    it("uses the T08 parser: kind 'http', raw preserved, RFC fields undefined, real status attached", async () => {
      const body = { message: "internal failure", code: "OOPS" };
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(500, body)));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect(caught).toMatchObject({
        kind: "http",
        status: 500,
        type: undefined,
        title: undefined,
        detail: undefined,
        instance: undefined,
        raw: body,
      });
      expect(typeof (caught as { message: string }).message).toBe("string");
      expect((caught as { message: string }).message.length).toBeGreaterThan(0);
    });
  });

  describe("F. Malformed / non-JSON HTTP error", () => {
    it("normalizes to kind 'parse', preserves the raw text, and never exposes raw server content as the safe message", async () => {
      const html = "<html><body>Bad Gateway</body></html>";
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(502, html)));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect(caught).toMatchObject({ kind: "parse", raw: html });
      const message = (caught as { message: string }).message;
      expect(message).not.toContain("<html>");
      expect(message).not.toContain("Bad Gateway");
      expect(message.length).toBeGreaterThan(0);
    });

    it("never throws a raw parser exception — the client itself resolves the failure into an ApiError", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(500, "")));

      await expect(apiClient.get("/api/health/ready")).rejects.toMatchObject({ kind: "parse" });
    });
  });

  describe("G. Network failure", () => {
    it("normalizes a rejected fetch (no response received) to kind 'network' with a safe fallback message", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect(caught).toMatchObject({ kind: "network" });
      const message = (caught as { message: string }).message;
      expect(message).not.toContain("Failed to fetch");
      expect(message.length).toBeGreaterThan(0);
    });
  });

  describe("H. Timeout", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    it("aborts the request at the configured timeout and normalizes to kind 'timeout', distinct from 'network'", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn((_input: unknown, init?: { signal?: AbortSignal }) => {
          return new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          });
        })
      );

      const pending = apiClient.get("/api/health/ready", { timeoutMs: 5000 });
      const assertion = expect(pending).rejects.toMatchObject({ kind: "timeout" });

      await vi.advanceTimersByTimeAsync(5000);
      await assertion;
    });

    it("does not fire before the configured timeout has elapsed", async () => {
      let settleWithSuccess: (() => void) | undefined;
      vi.stubGlobal(
        "fetch",
        vi.fn(() => {
          return new Promise((resolve) => {
            settleWithSuccess = () => resolve(jsonResponse(200, { ok: true }));
          });
        })
      );

      const pending = apiClient.get("/api/health/ready", { timeoutMs: 5000 });

      await vi.advanceTimersByTimeAsync(4000);
      expect(settleWithSuccess).toBeDefined();
      settleWithSuccess?.();

      await expect(pending).resolves.toEqual({ ok: true });
    });
  });

  // FVS-002 BATCH 3 Part A — FVS-002-IMPLEMENTATION-PLAN.md §1 row 13:
  // 429 responses carry a `Retry-After` header in whole seconds. Only a
  // parsed, validated seconds value is ever exposed — never a raw
  // Response/Headers object, never an invented value for a missing/
  // malformed header.
  describe("I. Retry-After header", () => {
    it("exposes retryAfterSeconds: 120 for Retry-After: 120", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "120" }))
      );

      await expect(apiClient.get("/api/health/ready")).rejects.toMatchObject({ retryAfterSeconds: 120 });
    });

    it("exposes retryAfterSeconds: 3599 for Retry-After: 3599", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "3599" }))
      );

      await expect(apiClient.get("/api/health/ready")).rejects.toMatchObject({ retryAfterSeconds: 3599 });
    });

    it("leaves retryAfterSeconds undefined when the header is missing", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(429, { type: "about:blank", status: 429 })));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
    });

    it("leaves retryAfterSeconds undefined for a malformed (non-whole-second) header value", async () => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "not-a-number" })
          )
      );

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
    });

    it("leaves retryAfterSeconds undefined for a negative header value", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "-5" }))
      );

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
    });

    it("leaves retryAfterSeconds undefined for a fractional-seconds header value", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "1.5" }))
      );

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
    });

    it("also exposes retryAfterSeconds on apiClient.post's thrown ApiError", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponseWithHeaders(429, { type: "about:blank", status: 429 }, { "Retry-After": "60" }))
      );

      await expect(apiClient.post("/api/v1/auth/resend-verification", { email: "a@example.com" })).rejects.toMatchObject({
        retryAfterSeconds: 60,
      });
    });
  });
});

// FVS002-T06 — apiClient.post reuses every success/failure rule get()
// already has (same path assertion, same timeout mechanism, same
// ApiError/parseProblemBody wiring, same safe fallback messages) plus JSON
// body serialization. Only cases genuinely specific to POST are repeated
// here in full; get()'s own 11 tests above already prove the shared
// machinery and must keep passing unchanged (regression).
describe("apiClient.post", () => {
  describe("A. Successful JSON response with a body", () => {
    it("serializes the body as JSON, sets Content-Type, and returns the parsed response directly", async () => {
      const fetchStub = vi.fn().mockResolvedValue(jsonResponse(201, { id: "abc123" }));
      vi.stubGlobal("fetch", fetchStub);

      const result = await apiClient.post("/api/v1/auth/register", { email: "a@example.com" });

      expect(result).toEqual({ id: "abc123" });
      expect(fetchStub).toHaveBeenCalledTimes(1);
      const [calledPath, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      expect(calledPath).toBe("/api/v1/auth/register");
      expect(calledInit.method).toBe("POST");
      expect(calledInit.body).toBe(JSON.stringify({ email: "a@example.com" }));
      expect(new Headers(calledInit.headers).get("Content-Type")).toBe("application/json");
    });
  });

  describe("B. No body supplied", () => {
    it("sends the request with no body and no Content-Type header", async () => {
      const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
      vi.stubGlobal("fetch", fetchStub);

      await apiClient.post("/api/v1/auth/verify-email");

      const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      expect(calledInit.method).toBe("POST");
      expect(calledInit.body).toBeUndefined();
      expect(new Headers(calledInit.headers).has("Content-Type")).toBe(false);
    });
  });

  describe("C. Successful empty/unparseable body", () => {
    it("resolves to undefined on a 2xx response with an empty body, same as get()", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(200, "")));

      const result = await apiClient.post("/api/v1/auth/register", { email: "a@example.com" });

      expect(result).toBeUndefined();
    });
  });

  describe("D. RFC 9457 HTTP error", () => {
    it("throws an ApiError with kind 'http', the confirmed RFC fields, and the real HTTP status", async () => {
      const problemBody = { type: "https://example.com/probs/validation", title: "Invalid", status: 422 };
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(422, problemBody)));

      await expect(apiClient.post("/api/v1/auth/register", {})).rejects.toMatchObject({
        kind: "http",
        status: 422,
        type: "https://example.com/probs/validation",
        title: "Invalid",
      });
    });
  });

  describe("E. Malformed / non-JSON HTTP error", () => {
    it("normalizes to kind 'parse', same as get()", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(502, "<html>Bad Gateway</html>")));

      await expect(apiClient.post("/api/v1/auth/register", {})).rejects.toMatchObject({ kind: "parse" });
    });
  });

  describe("F. Network failure", () => {
    it("normalizes to kind 'network', same as get()", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

      await expect(apiClient.post("/api/v1/auth/register", {})).rejects.toMatchObject({ kind: "network" });
    });
  });

  describe("G. Timeout", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    it("aborts at the configured timeout and normalizes to kind 'timeout', same mechanism as get()", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn((_input: unknown, init?: { signal?: AbortSignal }) => {
          return new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          });
        })
      );

      const pending = apiClient.post("/api/v1/auth/register", {}, { timeoutMs: 5000 });
      const assertion = expect(pending).rejects.toMatchObject({ kind: "timeout" });

      await vi.advanceTimersByTimeAsync(5000);
      await assertion;
    });
  });

  describe("H. Path enforcement", () => {
    it("rejects a path that does not start with /api/, same rule as get()", async () => {
      await expect(apiClient.post("/v1/auth/register", {})).rejects.toThrow('path must start with "/api/"');
    });
  });

  // FVS-003 BATCH 3A Part C — explicit opt-in CSRF support. Never a blanket
  // auto-attach: anonymous/login calls must stay byte-for-byte unaffected.
  describe("I. Explicit CSRF opt-in ({ csrf: true })", () => {
    afterEach(() => {
      document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
    });

    it("attaches X-CSRF-Token with the current cookie value when csrf: true is passed", async () => {
      document.cookie = "csrf_token=abc123";
      const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
      vi.stubGlobal("fetch", fetchStub);

      await apiClient.post("/api/v1/auth/refresh", undefined, { csrf: true });

      const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      expect(new Headers(calledInit.headers).get("X-CSRF-Token")).toBe("abc123");
    });

    it("re-reads the cookie fresh on every call — never caches a stale value across requests", async () => {
      const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
      vi.stubGlobal("fetch", fetchStub);

      document.cookie = "csrf_token=first-value";
      await apiClient.post("/api/v1/auth/refresh", undefined, { csrf: true });
      document.cookie = "csrf_token=second-value";
      await apiClient.post("/api/v1/auth/refresh", undefined, { csrf: true });

      const [, firstInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      const [, secondInit] = fetchStub.mock.calls[1] as [string, RequestInit];
      expect(new Headers(firstInit.headers).get("X-CSRF-Token")).toBe("first-value");
      expect(new Headers(secondInit.headers).get("X-CSRF-Token")).toBe("second-value");
    });

    it("fails locally with a safe, normalized ApiError (kind: 'csrf') when the cookie is missing — never invents a fake token, never sends the request", async () => {
      const fetchStub = vi.fn();
      vi.stubGlobal("fetch", fetchStub);

      await expect(apiClient.post("/api/v1/auth/refresh", undefined, { csrf: true })).rejects.toMatchObject({
        kind: "csrf",
      });
      expect(fetchStub).not.toHaveBeenCalled();
    });

    it("never attaches X-CSRF-Token when csrf is omitted (default), even if the cookie exists — no blanket auto-attach", async () => {
      document.cookie = "csrf_token=should-not-be-sent";
      const fetchStub = vi.fn().mockResolvedValue(jsonResponse(202, { message: "ok" }));
      vi.stubGlobal("fetch", fetchStub);

      await apiClient.post("/api/v1/auth/register", { email: "a@example.com", password: "password123" });

      const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      expect(new Headers(calledInit.headers).has("X-CSRF-Token")).toBe(false);
    });

    it("existing anonymous POST behavior (register) is completely unchanged — exact same body/headers as before", async () => {
      const fetchStub = vi.fn().mockResolvedValue(jsonResponse(202, { message: "ok" }));
      vi.stubGlobal("fetch", fetchStub);

      await apiClient.post("/api/v1/auth/register", { email: "a@example.com", password: "password123" });

      const [calledPath, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      expect(calledPath).toBe("/api/v1/auth/register");
      expect(calledInit.method).toBe("POST");
      expect(calledInit.body).toBe(JSON.stringify({ email: "a@example.com", password: "password123" }));
      expect(new Headers(calledInit.headers).get("Content-Type")).toBe("application/json");
      expect(new Headers(calledInit.headers).has("X-CSRF-Token")).toBe(false);
    });

    it("csrf: true with a body still sets both Content-Type and X-CSRF-Token", async () => {
      document.cookie = "csrf_token=xyz";
      const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
      vi.stubGlobal("fetch", fetchStub);

      await apiClient.post("/api/v1/auth/logout", undefined, { csrf: true });

      const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
      const headers = new Headers(calledInit.headers);
      expect(headers.get("X-CSRF-Token")).toBe("xyz");
    });
  });
});

// Phase 2 auth/account batch — notifications' `PATCH /me/notifications/{id}`
// is the first confirmed endpoint that needs PATCH; apiClient.patch reuses
// every shared mechanism get()/post() already prove (path assertion,
// timeout, ApiError wiring, CSRF opt-in) — only PATCH-specific cases are
// repeated here in full.
describe("apiClient.patch", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  it("serializes the body as JSON, sets Content-Type, uses method PATCH, and returns the parsed response", async () => {
    const fetchStub = vi.fn().mockResolvedValue(jsonResponse(200, { id: "n1", read: true }));
    vi.stubGlobal("fetch", fetchStub);

    document.cookie = "csrf_token=anything";
    const result = await apiClient.patch("/api/v1/me/notifications/n1", { read: true }, { csrf: true });

    expect(result).toEqual({ id: "n1", read: true });
    const [calledPath, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(calledPath).toBe("/api/v1/me/notifications/n1");
    expect(calledInit.method).toBe("PATCH");
    expect(calledInit.body).toBe(JSON.stringify({ read: true }));
    expect(new Headers(calledInit.headers).get("Content-Type")).toBe("application/json");
  });

  it("attaches X-CSRF-Token with the current cookie value when csrf: true is passed", async () => {
    document.cookie = "csrf_token=abc123";
    const fetchStub = vi.fn().mockResolvedValue(jsonResponse(200, { id: "n1", read: true }));
    vi.stubGlobal("fetch", fetchStub);

    await apiClient.patch("/api/v1/me/notifications/n1", { read: true }, { csrf: true });

    const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(new Headers(calledInit.headers).get("X-CSRF-Token")).toBe("abc123");
  });

  it("fails locally with kind: 'csrf' when the cookie is missing and csrf: true is requested — never sends the request", async () => {
    const fetchStub = vi.fn();
    vi.stubGlobal("fetch", fetchStub);

    await expect(apiClient.patch("/api/v1/me/notifications/n1", { read: true }, { csrf: true })).rejects.toMatchObject(
      { kind: "csrf" }
    );
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("never attaches X-CSRF-Token when csrf is omitted, even if the cookie exists", async () => {
    document.cookie = "csrf_token=should-not-be-sent";
    const fetchStub = vi.fn().mockResolvedValue(jsonResponse(200, { id: "n1", read: true }));
    vi.stubGlobal("fetch", fetchStub);

    await apiClient.patch("/api/v1/me/notifications/n1", { read: true });

    const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(new Headers(calledInit.headers).has("X-CSRF-Token")).toBe(false);
  });

  it("throws an ApiError with kind 'http' and the real status on an RFC 9457 error", async () => {
    document.cookie = "csrf_token=abc123";
    const problemBody = { type: "about:blank", title: "Forbidden", status: 403, code: "CSRF_INVALID" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(403, problemBody)));

    await expect(apiClient.patch("/api/v1/me/notifications/n1", { read: true }, { csrf: true })).rejects.toMatchObject(
      { kind: "http", status: 403, code: "CSRF_INVALID" }
    );
  });

  it("resolves to undefined on a 2xx response with an empty body", async () => {
    document.cookie = "csrf_token=abc123";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(textResponse(204, "")));

    const result = await apiClient.patch("/api/v1/me/notifications/n1", { read: true }, { csrf: true });

    expect(result).toBeUndefined();
  });

  it("rejects a path that does not start with /api/, same rule as get()/post()", async () => {
    await expect(apiClient.patch("/v1/me/notifications/n1", { read: true })).rejects.toThrow(
      'path must start with "/api/"'
    );
  });
});

// Phase 3 — admin product DELETE needs a query-string version
// (?version=N) and the same CSRF/problem/timeout machinery every other
// write already has. No request body is ever sent on DELETE.
describe("apiClient.del", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  it("sends method DELETE with no body and returns the parsed response", async () => {
    const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
    vi.stubGlobal("fetch", fetchStub);
    document.cookie = "csrf_token=abc123";

    const result = await apiClient.del("/api/v1/admin/products/p1", { csrf: true });

    expect(result).toBeUndefined();
    const [calledPath, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(calledPath).toBe("/api/v1/admin/products/p1");
    expect(calledInit.method).toBe("DELETE");
    expect(calledInit.body).toBeUndefined();
  });

  it("appends a query string built from the query option", async () => {
    const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
    vi.stubGlobal("fetch", fetchStub);
    document.cookie = "csrf_token=abc123";

    await apiClient.del("/api/v1/admin/products/p1", { csrf: true, query: { version: 3 } });

    const [calledPath] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(calledPath).toBe("/api/v1/admin/products/p1?version=3");
  });

  it("attaches X-CSRF-Token when csrf: true is passed", async () => {
    document.cookie = "csrf_token=abc123";
    const fetchStub = vi.fn().mockResolvedValue(textResponse(204, ""));
    vi.stubGlobal("fetch", fetchStub);

    await apiClient.del("/api/v1/admin/products/p1", { csrf: true, query: { version: 1 } });

    const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(new Headers(calledInit.headers).get("X-CSRF-Token")).toBe("abc123");
  });

  it("fails locally with kind: 'csrf' when the cookie is missing and csrf: true is requested — never sends the request", async () => {
    const fetchStub = vi.fn();
    vi.stubGlobal("fetch", fetchStub);

    await expect(apiClient.del("/api/v1/admin/products/p1", { csrf: true })).rejects.toMatchObject({ kind: "csrf" });
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("throws an ApiError with the real status and code on a 409 VERSION_CONFLICT", async () => {
    document.cookie = "csrf_token=abc123";
    const problemBody = { type: "about:blank", title: "Conflict", status: 409, code: "VERSION_CONFLICT" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(409, problemBody)));

    await expect(
      apiClient.del("/api/v1/admin/products/p1", { csrf: true, query: { version: 1 } })
    ).rejects.toMatchObject({ kind: "http", status: 409, code: "VERSION_CONFLICT" });
  });

  it("rejects a path that does not start with /api/, same rule as the other verbs", async () => {
    await expect(apiClient.del("/v1/admin/products/p1")).rejects.toThrow('path must start with "/api/"');
  });
});

// Phase 3 — admin product-image upload is multipart/form-data: the
// browser must set its own Content-Type (with boundary), so postForm must
// never set Content-Type itself, unlike post()/patch()'s JSON bodies.
describe("apiClient.postForm", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  it("sends the FormData body as-is, with method POST and no Content-Type header set", async () => {
    document.cookie = "csrf_token=abc123";
    const fetchStub = vi.fn().mockResolvedValue(jsonResponse(201, { id: "img1" }));
    vi.stubGlobal("fetch", fetchStub);

    const formData = new FormData();
    formData.append("file", new Blob(["x"]), "photo.png");

    const result = await apiClient.postForm("/api/v1/admin/products/p1/images", formData, { csrf: true });

    expect(result).toEqual({ id: "img1" });
    const [calledPath, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(calledPath).toBe("/api/v1/admin/products/p1/images");
    expect(calledInit.method).toBe("POST");
    expect(calledInit.body).toBe(formData);
    expect(new Headers(calledInit.headers).has("Content-Type")).toBe(false);
  });

  it("attaches X-CSRF-Token when csrf: true is passed", async () => {
    document.cookie = "csrf_token=abc123";
    const fetchStub = vi.fn().mockResolvedValue(jsonResponse(201, { id: "img1" }));
    vi.stubGlobal("fetch", fetchStub);

    await apiClient.postForm("/api/v1/admin/products/p1/images", new FormData(), { csrf: true });

    const [, calledInit] = fetchStub.mock.calls[0] as [string, RequestInit];
    expect(new Headers(calledInit.headers).get("X-CSRF-Token")).toBe("abc123");
  });

  it("fails locally with kind: 'csrf' when the cookie is missing and csrf: true is requested — never sends the request", async () => {
    const fetchStub = vi.fn();
    vi.stubGlobal("fetch", fetchStub);

    await expect(
      apiClient.postForm("/api/v1/admin/products/p1/images", new FormData(), { csrf: true })
    ).rejects.toMatchObject({ kind: "csrf" });
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("surfaces UPLOAD_REJECTED as an ApiError with kind 'http' and the real status", async () => {
    document.cookie = "csrf_token=abc123";
    const problemBody = { type: "about:blank", title: "Upload rejected", status: 422, code: "UPLOAD_REJECTED" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(422, problemBody)));

    await expect(
      apiClient.postForm("/api/v1/admin/products/p1/images", new FormData(), { csrf: true })
    ).rejects.toMatchObject({ kind: "http", status: 422, code: "UPLOAD_REJECTED" });
  });

  it("rejects a path that does not start with /api/, same rule as the other verbs", async () => {
    await expect(apiClient.postForm("/v1/admin/products/p1/images", new FormData())).rejects.toThrow(
      'path must start with "/api/"'
    );
  });
});

// Phase 5D (FVS-026) — POST /api/v1/checkout requires an `Idempotency-Key`
// request header. `headers` is an explicit per-call opt-in on post() only;
// it can never override Content-Type or the CSRF header.
describe("apiClient.post extra headers (Phase 5D)", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  it("sends a caller-supplied header alongside Content-Type and X-CSRF-Token", async () => {
    document.cookie = "csrf_token=tok-1";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.post("/api/v1/checkout", { a: 1 }, { csrf: true, headers: { "Idempotency-Key": "key-12345" } });

    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.headers).toEqual({
      "Idempotency-Key": "key-12345",
      "Content-Type": "application/json",
      "X-CSRF-Token": "tok-1",
    });
  });

  it("never lets a caller header override Content-Type or the CSRF token", async () => {
    document.cookie = "csrf_token=real";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.post(
      "/api/v1/checkout",
      { a: 1 },
      {
        csrf: true,
        headers: { "Content-Type": "text/plain", "X-CSRF-Token": "forged" },
      }
    );

    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["X-CSRF-Token"]).toBe("real");
  });

  it("sends no header object at all when none is needed (unchanged default)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiClient.post("/api/v1/thing");
    expect((fetchMock.mock.calls[0]![1] as RequestInit).headers).toBeUndefined();
  });
});
