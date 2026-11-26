import { describe, it, expect } from "vitest";
import { isSafeReturnTo, resolveReturnTo, buildLoginRedirectPath } from "./returnTo";

// FVS-003-IMPLEMENTATION-PLAN.md §12 — a safe, same-origin-relative-path-only
// validator, fully pure (no `window`, no DOM, no router dependency), so it
// is also usable server-side later if ever needed. This is this slice's own
// architecture decision (§2 row 39), not contract-dependent on anything the
// backend confirms.

describe("isSafeReturnTo", () => {
  it.each([
    ["/", "root"],
    ["/account", "normal nested relative route"],
    ["/account/orders", "deeper nested relative route"],
    ["/shop/item?tab=details", "query string preserved"],
    ["/path#section", "hash preserved"],
  ])("accepts %s (%s)", (value) => {
    expect(isSafeReturnTo(value)).toBe(true);
  });

  it.each([
    ["https://evil.example", "absolute https URL"],
    ["http://evil.example", "absolute http URL"],
    ["//evil.example", "protocol-relative URL"],
    ["///evil.example", "triple-slash protocol-relative URL"],
    ["javascript:alert(1)", "javascript: pseudo-protocol"],
    ["data:text/html,<script>alert(1)</script>", "data: URL"],
    ["\\evil.example", "leading backslash trick"],
    ["/\\evil.example", "slash-then-backslash trick"],
    ["/%5C%5Cevil.example", "percent-encoded backslash trick"],
    ["/%2F%2Fevil.example", "percent-encoded protocol-relative attempt"],
    ["/%2Fevil.example", "single percent-encoded slash forming //"],
    ["", "empty string"],
    ["not a path at all", "non-path garbage"],
    ["   ", "whitespace-only garbage"],
    ["ftp://evil.example", "a non-http(s) absolute protocol"],
  ])("rejects %s (%s)", (value) => {
    expect(isSafeReturnTo(value)).toBe(false);
  });

  it("does not throw on malformed percent-encoding", () => {
    expect(() => isSafeReturnTo("/%")).not.toThrow();
    expect(() => isSafeReturnTo("/%zz")).not.toThrow();
    expect(() => isSafeReturnTo("/%E0%A4%A")).not.toThrow();
    expect(isSafeReturnTo("/%")).toBe(false);
    expect(isSafeReturnTo("/%zz")).toBe(false);
  });

  it("rejects a non-string value without throwing", () => {
    // `isSafeReturnTo` deliberately accepts `unknown` (not `string`) so this
    // runtime boundary check — e.g. a query param that could theoretically
    // be null/undefined before this function is ever called — is itself a
    // real, type-checked call, not a suppressed one.
    expect(isSafeReturnTo(null)).toBe(false);
    expect(isSafeReturnTo(undefined)).toBe(false);
  });
});

describe("resolveReturnTo", () => {
  it("returns a safe value unchanged", () => {
    expect(resolveReturnTo("/account/orders")).toBe("/account/orders");
    expect(resolveReturnTo("/shop/item?tab=details")).toBe("/shop/item?tab=details");
    expect(resolveReturnTo("/path#section")).toBe("/path#section");
  });

  it("falls back to / for every rejected value", () => {
    expect(resolveReturnTo("https://evil.example")).toBe("/");
    expect(resolveReturnTo("//evil.example")).toBe("/");
    expect(resolveReturnTo("")).toBe("/");
  });

  it("falls back to / for null/undefined", () => {
    expect(resolveReturnTo(null)).toBe("/");
    expect(resolveReturnTo(undefined)).toBe("/");
  });
});

describe("buildLoginRedirectPath", () => {
  it("builds /login?returnTo=<encoded-safe-path> for a safe value", () => {
    expect(buildLoginRedirectPath("/account/orders")).toBe("/login?returnTo=%2Faccount%2Forders");
  });

  it("encodes query strings and hashes inside the safe path correctly", () => {
    expect(buildLoginRedirectPath("/shop/item?tab=details")).toBe(
      "/login?returnTo=%2Fshop%2Fitem%3Ftab%3Ddetails"
    );
  });

  it("falls back to a plain /login?returnTo=%2F for an unsafe value, never embedding the attack string", () => {
    const result = buildLoginRedirectPath("https://evil.example");
    expect(result).toBe("/login?returnTo=%2F");
    expect(result).not.toContain("evil.example");
  });

  it("falls back the same way for a missing value", () => {
    expect(buildLoginRedirectPath(null)).toBe("/login?returnTo=%2F");
    expect(buildLoginRedirectPath(undefined)).toBe("/login?returnTo=%2F");
  });
});
