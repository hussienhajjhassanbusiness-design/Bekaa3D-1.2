import { describe, it, expect, vi, afterEach } from "vitest";
import { extractResetToken, removeTokenFromUrl } from "./passwordResetToken";

// Phase 2 auth/account batch — correction to FVS-004's original
// implementation: AGENTS.md's confirmed reset-link format is
// `/reset-password#token=...` — the token lives in the URL FRAGMENT, read
// via `location.hash`, never a query parameter (a fragment is never sent
// to the server, which is exactly why the backend chose it for a
// bearer-style credential). The token's content is otherwise fully
// opaque: no format, length, or alphabet is assumed anywhere in these
// tests.

describe("extractResetToken", () => {
  it("accepts exactly one non-empty token from a leading-# hash string", () => {
    expect(extractResetToken("#token=abc123")).toBe("abc123");
  });

  it("also accepts the hash content without a leading #", () => {
    expect(extractResetToken("token=abc123")).toBe("abc123");
  });

  it("rejects a missing token (fails closed, returns null)", () => {
    expect(extractResetToken("")).toBeNull();
    expect(extractResetToken("#")).toBeNull();
    expect(extractResetToken("#other=value")).toBeNull();
  });

  it("rejects an empty token value", () => {
    expect(extractResetToken("#token=")).toBeNull();
  });

  it("rejects multiple token parameters (never guesses which is correct)", () => {
    expect(extractResetToken("#token=a&token=b")).toBeNull();
  });

  it("returns the token's content unchanged", () => {
    expect(extractResetToken("#token=AbC-123_XYZ.~")).toBe("AbC-123_XYZ.~");
  });

  it("does not silently trim a token containing spaces", () => {
    expect(extractResetToken(`#token=${encodeURIComponent(" abc ")}`)).toBe(" abc ");
  });

  it("leaves punctuation in the token unchanged", () => {
    expect(extractResetToken("#token=a.b-c_d~e!f*g")).toBe("a.b-c_d~e!f*g");
  });

  it("follows URLSearchParams' own percent-decoding semantics, with no additional normalization", () => {
    // %2B decodes to a literal "+" — standard URLSearchParams decoding,
    // not something this helper invents or alters.
    expect(extractResetToken("#token=a%2Bb")).toBe("a+b");
    // A literal "+" is itself decoded to a space by
    // application/x-www-form-urlencoded rules — again standard behavior.
    expect(extractResetToken("#token=a+b")).toBe("a b");
  });

  it("never throws on malformed/edge input", () => {
    expect(() => extractResetToken("#token")).not.toThrow();
    expect(() => extractResetToken("#%zz=%zz")).not.toThrow();
    expect(extractResetToken("#token=&token=")).toBeNull();
  });

  describe("storage", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("never touches localStorage or sessionStorage", () => {
      const localSpy = vi.spyOn(Storage.prototype, "setItem");
      extractResetToken("#token=abc123");
      expect(localSpy).not.toHaveBeenCalled();
    });
  });
});

describe("removeTokenFromUrl", () => {
  it("removes the entire hash (the token's only location)", () => {
    expect(removeTokenFromUrl("/reset-password#token=abc123")).toBe("/reset-password");
  });

  it("preserves unrelated query parameters", () => {
    expect(removeTokenFromUrl("/reset-password?lang=en#token=abc123")).toBe("/reset-password?lang=en");
  });

  it("preserves the pathname", () => {
    expect(removeTokenFromUrl("/reset-password/deep#token=abc123")).toBe("/reset-password/deep");
  });

  it("never leaves the literal token value anywhere in the sanitized output", () => {
    const sanitized = removeTokenFromUrl("/reset-password#token=super-secret-value-123");
    expect(sanitized).not.toContain("super-secret-value-123");
    expect(sanitized).not.toContain("token");
  });

  it("is a no-op when there is no hash to remove", () => {
    expect(removeTokenFromUrl("/reset-password")).toBe("/reset-password");
    expect(removeTokenFromUrl("/reset-password?lang=en")).toBe("/reset-password?lang=en");
  });

  it("never throws on malformed/edge input", () => {
    expect(() => removeTokenFromUrl("")).not.toThrow();
    expect(() => removeTokenFromUrl("not a url at all")).not.toThrow();
    expect(() => removeTokenFromUrl("/reset-password#token=a&token=b")).not.toThrow();
  });

  it("never touches localStorage or sessionStorage", () => {
    const localSpy = vi.spyOn(Storage.prototype, "setItem");
    removeTokenFromUrl("/reset-password#token=abc123");
    expect(localSpy).not.toHaveBeenCalled();
    localSpy.mockRestore();
  });
});
