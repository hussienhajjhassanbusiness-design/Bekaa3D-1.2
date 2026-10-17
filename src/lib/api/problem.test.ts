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
        ["code", "detail", "errors", "instance", "kind", "message", "raw", "status", "title", "type"].sort()
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

  describe("FVS-003 BATCH 3A Part B — top-level problem `code` field", () => {
    it.each([
      ["401", "AUTH_REQUIRED", 401, "AUTH_REQUIRED"],
      ["401", "MFA_REQUIRED", 401, "MFA_REQUIRED"],
      ["403", "CSRF_INVALID", 403, "CSRF_INVALID"],
      ["429", "RATE_LIMITED", 429, "RATE_LIMITED"],
    ])("%s + %s: code is preserved exactly", (_label, _codeLabel, status, code) => {
      const body = JSON.stringify({ type: "about:blank", status, code });
      const result = parseProblemBody(body);

      expect(result.code).toBe(code);
      expect(result.status).toBe(status);
    });

    it("leaves code undefined when the body has no code field", () => {
      const result = parseProblemBody(JSON.stringify({ type: "about:blank", status: 500 }));

      expect(result.code).toBeUndefined();
    });

    it("leaves code undefined when the code field is present but not a string (never coerced)", () => {
      const result = parseProblemBody(JSON.stringify({ status: 401, code: 123 }));

      expect(result.code).toBeUndefined();
    });

    it("leaves code undefined for a non-problem or malformed body, same as the other RFC fields", () => {
      expect(parseProblemBody(JSON.stringify({ foo: "bar" })).code).toBeUndefined();
      expect(parseProblemBody("<html>Bad Gateway</html>").code).toBeUndefined();
    });
  });

  describe("A wrong-shaped 'errors' member is never coerced into the confirmed contract", () => {
    it("leaves errors undefined when the body's 'errors' value isn't an array (e.g. an object keyed by field)", () => {
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
      // The unrecognized-shape extension is visible ONLY inside the
      // untouched raw value — never coerced onto the typed `errors` field.
      expect((result.raw as { errors: unknown }).errors).toEqual({ email: ["is required"] });
      expect(result.errors).toBeUndefined();
    });

    it("leaves errors undefined when the array contains items missing loc/msg/type", () => {
      const body = JSON.stringify({ status: 422, errors: [{ msg: "Field required" }] });

      const result = parseProblemBody(body);

      expect(result.errors).toBeUndefined();
    });
  });

  describe("Confirmed 'errors[]' field (openapi.json Problem + ValidationError schemas)", () => {
    it("parses a well-formed errors array into typed loc/msg/type items", () => {
      const body = JSON.stringify({
        type: "about:blank",
        title: "Unprocessable Entity",
        status: 422,
        detail: "Validation failed",
        instance: "/api/v1/auth/register",
        code: "VALIDATION_ERROR",
        errors: [
          { loc: ["body", "email"], msg: "field required", type: "missing" },
          { loc: ["body", "password"], msg: "String should have at least 8 characters", type: "string_too_short" },
        ],
      });

      const result = parseProblemBody(body);

      expect(result.errors).toEqual([
        { loc: ["body", "email"], msg: "field required", type: "missing" },
        { loc: ["body", "password"], msg: "String should have at least 8 characters", type: "string_too_short" },
      ]);
    });

    it("parses an empty errors array as an empty array, not undefined", () => {
      const result = parseProblemBody(JSON.stringify({ status: 401, errors: [] }));

      expect(result.errors).toEqual([]);
    });

    it("accepts a numeric loc segment (e.g. an array index) alongside string segments", () => {
      const body = JSON.stringify({
        errors: [{ loc: ["body", "lines", 0, "quantity"], msg: "must be positive", type: "greater_than" }],
      });

      const result = parseProblemBody(body);

      expect(result.errors).toEqual([
        { loc: ["body", "lines", 0, "quantity"], msg: "must be positive", type: "greater_than" },
      ]);
    });

    it("leaves errors undefined when the field is absent entirely", () => {
      const result = parseProblemBody(JSON.stringify({ status: 500, detail: "boom" }));

      expect(result.errors).toBeUndefined();
    });
  });
});
