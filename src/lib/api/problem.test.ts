import { describe, it, expect } from "vitest";
import { parseProblemBody } from "./problem";

// Per bekaa3d-api-contract: this parser supports ONLY the five confirmed
// RFC 9457 fields (type/title/status/detail/instance — FRONTEND-VERTICAL-
// SLICE-PLAN.md §14). It must never invent, type, or normalize an
// `errors[]`/field-validation extension shape — that remains
// NEEDS BACKEND CONFIRMATION (§17) and, if present, is only ever visible
// unmodified inside `raw`.

describe("parseProblemBody", () => {
  describe("Case A — valid RFC 9457 object (all five confirmed fields present)", () => {
    const body = JSON.stringify({
      type: "https://example.com/probs/not-ready",
      title: "Not Ready",
      status: 503,
      detail: "Database unavailable",
      instance: "/health/ready",
    });

    it("populates every confirmed field with its exact value", () => {
      const result = parseProblemBody(body);

      expect(result.type).toBe("https://example.com/probs/not-ready");
      expect(result.title).toBe("Not Ready");
      expect(result.status).toBe(503);
      expect(result.detail).toBe("Database unavailable");
      expect(result.instance).toBe("/health/ready");
    });

    it("preserves the full parsed object in raw and never invents fields", () => {
      const result = parseProblemBody(body);

      expect(result.raw).toEqual({
        type: "https://example.com/probs/not-ready",
        title: "Not Ready",
        status: 503,
        detail: "Database unavailable",
        instance: "/health/ready",
      });
      // No field exists on the result beyond what ApiError itself defines.
      expect(Object.keys(result).sort()).toEqual(
        ["detail", "instance", "kind", "message", "raw", "status", "title", "type"].sort()
      );
    });

    it("leaves correlationId undefined — never populated by T08 (NEEDS BACKEND CONFIRMATION)", () => {
      const result = parseProblemBody(body);

      expect(result.correlationId).toBeUndefined();
    });

    it("requires a non-empty message (a required ApiError field), without inventing UX copy from detail", () => {
      const result = parseProblemBody(body);

      expect(typeof result.message).toBe("string");
      expect(result.message.length).toBeGreaterThan(0);
      // The required `message` field must never just be the raw `detail`
      // text verbatim — that's explicitly a later, status-aware UI concern.
      expect(result.message).not.toBe("Database unavailable");
    });
  });

  describe("Case B — partial RFC 9457 object (some confirmed fields absent)", () => {
    const body = JSON.stringify({ title: "Not Ready", status: 503 });

    it("populates only the present fields; absent ones stay undefined (never defaulted)", () => {
      const result = parseProblemBody(body);

      expect(result.title).toBe("Not Ready");
      expect(result.status).toBe(503);
      expect(result.type).toBeUndefined();
      expect(result.detail).toBeUndefined();
      expect(result.instance).toBeUndefined();
    });
  });

  describe("Case C — non-problem JSON (valid JSON, but none of the confirmed fields present)", () => {
    it.each([
      ["a plain object with unrelated keys", '{"foo":"bar"}', { foo: "bar" }],
      ["an array", "[1,2,3]", [1, 2, 3]],
      ["a JSON string primitive", '"just a string"', "just a string"],
      ["a JSON number primitive", "42", 42],
      ["a JSON boolean primitive", "true", true],
      ["JSON null", "null", null],
    ])("%s: all RFC fields stay undefined, raw preserves the exact parsed value", (_label, json, expectedRaw) => {
      const result = parseProblemBody(json);

      expect(result.type).toBeUndefined();
      expect(result.title).toBeUndefined();
      expect(result.status).toBeUndefined();
      expect(result.detail).toBeUndefined();
      expect(result.instance).toBeUndefined();
      expect(result.raw).toEqual(expectedRaw);
    });
  });

  describe("Case D — malformed / non-JSON body", () => {
    it.each([
      ["an HTML error page", "<html><body>Internal Server Error</body></html>"],
      ["truncated/invalid JSON", '{"type": "https://example.com/probs/'],
      ["an empty body", ""],
    ])("%s: kind is 'parse', raw text is preserved exactly, and it never throws", (_label, rawText) => {
      expect(() => parseProblemBody(rawText)).not.toThrow();

      const result = parseProblemBody(rawText);

      expect(result.kind).toBe("parse");
      expect(result.raw).toBe(rawText);
      expect(result.type).toBeUndefined();
      expect(result.title).toBeUndefined();
      expect(result.status).toBeUndefined();
      expect(result.detail).toBeUndefined();
      expect(result.instance).toBeUndefined();
    });
  });

  describe("Type-guard strictness — wrong-typed fields are rejected, never coerced", () => {
    it("does not coerce a string 'status' into a number", () => {
      const result = parseProblemBody(JSON.stringify({ status: "503" }));

      expect(result.status).toBeUndefined();
    });

    it("does not coerce a numeric 'title' into a string", () => {
      const result = parseProblemBody(JSON.stringify({ title: 123 }));

      expect(result.title).toBeUndefined();
    });

    it("does not coerce a numeric 'detail' into a string", () => {
      const result = parseProblemBody(JSON.stringify({ detail: 404 }));

      expect(result.detail).toBeUndefined();
    });
  });

  describe("Unknown extension members (e.g. a future errors[] shape) are never invented into a typed contract", () => {
    it("preserves an unrecognized 'errors' member unmodified inside raw, with no dedicated typed property on the result", () => {
      const body = JSON.stringify({
        type: "https://example.com/probs/validation",
        title: "Validation failed",
        status: 422,
        errors: { email: ["is required"] },
      });

      const result = parseProblemBody(body);

      // The five confirmed fields are still recognized normally.
      expect(result.type).toBe("https://example.com/probs/validation");
      expect(result.title).toBe("Validation failed");
      expect(result.status).toBe(422);
      // The unknown extension is visible ONLY inside the untouched raw value.
      expect((result.raw as { errors: unknown }).errors).toEqual({ email: ["is required"] });
      // ApiError itself has no invented `errors` property — this is the
      // exact contract-invention bekaa3d-api-contract forbids.
      expect("errors" in result).toBe(false);
    });
  });
});
