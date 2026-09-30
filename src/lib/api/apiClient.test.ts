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

    it("never populates correlationId and never invents an errors[] property", async () => {
      const problemBody = { type: "https://example.com/probs/not-ready", title: "Not Ready", status: 503 };
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, problemBody)));

      let caught: unknown;
      try {
        await apiClient.get("/api/health/ready");
      } catch (error) {
        caught = error;
      }

      expect((caught as { correlationId?: string }).correlationId).toBeUndefined();
      expect(caught && "errors" in (caught as object)).toBe(false);
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
});
