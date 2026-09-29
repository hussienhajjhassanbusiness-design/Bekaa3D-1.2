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
});
