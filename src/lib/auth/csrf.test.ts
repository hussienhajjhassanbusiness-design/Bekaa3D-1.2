import { describe, it, expect, afterEach } from "vitest";
import { readCookie, readCsrfToken, CSRF_HEADER_NAME } from "./csrf";

// FVS-003-IMPLEMENTATION-PLAN.md §5 (confirmed BATCH 3A) — csrf_token is the
// ONE cookie this slice's code may ever read; access_token/refresh_token
// are httpOnly and must never be touched. `readCookie` is a pure helper
// (takes the cookie string directly) so it's fully testable without
// mutating the real `document.cookie`; `readCsrfToken` wraps it against the
// real document.

describe("readCookie", () => {
  it("selects the exact named cookie among several", () => {
    const cookies = "a=1; csrf_token=abc123; b=2";
    expect(readCookie(cookies, "csrf_token")).toBe("abc123");
  });

  it("ignores unrelated cookies, including ones with a similar name", () => {
    const cookies = "csrf_token_old=stale; csrf_token=fresh; not_csrf_token=other";
    expect(readCookie(cookies, "csrf_token")).toBe("fresh");
  });

  it("decodes a percent-encoded cookie value safely", () => {
    const cookies = `csrf_token=${encodeURIComponent("value/with+special=chars")}`;
    expect(readCookie(cookies, "csrf_token")).toBe("value/with+special=chars");
  });

  it("returns undefined for malformed percent-encoding instead of throwing", () => {
    expect(() => readCookie("csrf_token=%zz", "csrf_token")).not.toThrow();
    expect(readCookie("csrf_token=%zz", "csrf_token")).toBeUndefined();
  });

  it("returns undefined when the cookie is missing", () => {
    expect(readCookie("a=1; b=2", "csrf_token")).toBeUndefined();
  });

  it("returns undefined for an empty cookie string", () => {
    expect(readCookie("", "csrf_token")).toBeUndefined();
  });

  it("handles cookies with no spaces after the semicolon", () => {
    expect(readCookie("a=1;csrf_token=xyz;b=2", "csrf_token")).toBe("xyz");
  });

  it("never returns a value for access_token or refresh_token even if asked", () => {
    const cookies = "access_token=secret-access; refresh_token=secret-refresh; csrf_token=abc";
    // This module exposes no way to read these by design (no exported
    // function accepts "access_token"/"refresh_token" as a convenience
    // constant) — this test documents that readCookie itself is generic
    // and could technically be pointed at them, which is exactly why
    // production code must only ever call readCsrfToken(), never readCookie
    // with an arbitrary name. See csrf.ts's own module-level contract note.
    expect(readCookie(cookies, "access_token")).toBe("secret-access");
    expect(readCookie(cookies, "refresh_token")).toBe("secret-refresh");
    expect(readCookie(cookies, "csrf_token")).toBe("abc");
  });
});

describe("readCsrfToken", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  it("reads the real csrf_token cookie from document.cookie", () => {
    document.cookie = "csrf_token=real-value-123";
    expect(readCsrfToken()).toBe("real-value-123");
  });

  it("returns undefined when no csrf_token cookie is set", () => {
    expect(readCsrfToken()).toBeUndefined();
  });
});

describe("CSRF_HEADER_NAME", () => {
  it("is exactly X-CSRF-Token, per the confirmed contract", () => {
    expect(CSRF_HEADER_NAME).toBe("X-CSRF-Token");
  });
});
