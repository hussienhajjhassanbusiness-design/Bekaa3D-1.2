import { describe, it, expect, vi, afterEach } from "vitest";
import { extractResetToken, removeTokenFromUrl } from "./passwordResetToken";

// FVS-004-IMPLEMENTATION-PLAN.md T01 (CAN IMPLEMENT NOW — contract-
// independent) — the `token` query-parameter name is the only thing
// FVS-004 confirms about the reset link (FRONTEND-VERTICAL-SLICE-PLAN.md's
// own routing table). The token's content is fully opaque: no format,
// length, or alphabet is assumed anywhere in these tests.

describe("extractResetToken", () => {
  it("accepts exactly one non-empty token", () => {
    expect(extractResetToken(new URLSearchParams("token=abc123"))).toBe("abc123");
  });

  it("rejects a missing token (fails closed, returns null)", () => {
    expect(extractResetToken(new URLSearchParams(""))).toBeNull();
    expect(extractResetToken(new URLSearchParams("other=value"))).toBeNull();
  });

  it("rejects an empty token value", () => {
    expect(extractResetToken(new URLSearchParams("token="))).toBeNull();
  });

  it("rejects multiple token parameters (never guesses which is correct)", () => {
    expect(extractResetToken(new URLSearchParams("token=a&token=b"))).toBeNull();
  });

  it("returns the token's content unchanged", () => {
    expect(extractResetToken(new URLSearchParams("token=AbC-123_XYZ.~"))).toBe("AbC-123_XYZ.~");
  });

  it("does not silently trim a token containing spaces", () => {
    const params = new URLSearchParams();
    params.set("token", " abc ");
    expect(extractResetToken(params)).toBe(" abc ");
  });

  it("leaves punctuation in the token unchanged", () => {
    const params = new URLSearchParams();
    params.set("token", "a.b-c_d~e!f*g");
    expect(extractResetToken(params)).toBe("a.b-c_d~e!f*g");
  });

  it("follows URLSearchParams' own percent-decoding semantics, with no additional normalization", () => {
    // %2B decodes to a literal "+" — this is URLSearchParams' own standard
    // decoding, not something this helper invents or alters.
    expect(extractResetToken(new URLSearchParams("token=a%2Bb"))).toBe("a+b");
    // A literal "+" in a query string is itself decoded to a space by
    // application/x-www-form-urlencoded rules — again, standard
    // URLSearchParams behavior, not this helper's own choice.
    expect(extractResetToken(new URLSearchParams("token=a+b"))).toBe("a b");
  });

  it("never throws on malformed/edge input", () => {
    expect(() => extractResetToken(new URLSearchParams("token"))).not.toThrow();
    expect(() => extractResetToken(new URLSearchParams("%zz=%zz"))).not.toThrow();
    expect(extractResetToken(new URLSearchParams("token=&token="))).toBeNull();
  });

  describe("storage", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("never touches localStorage or sessionStorage", () => {
      const localSpy = vi.spyOn(Storage.prototype, "setItem");
      extractResetToken(new URLSearchParams("token=abc123"));
      expect(localSpy).not.toHaveBeenCalled();
    });
  });
});

describe("removeTokenFromUrl", () => {
  it("removes the token query parameter", () => {
    expect(removeTokenFromUrl("/reset-password?token=abc123")).toBe("/reset-password");
  });

  it("preserves unrelated query parameters", () => {
    expect(removeTokenFromUrl("/reset-password?lang=en&token=abc123")).toBe("/reset-password?lang=en");
  });

  it("preserves the pathname", () => {
    expect(removeTokenFromUrl("/reset-password/deep?token=abc123")).toBe("/reset-password/deep");
  });

  it("preserves the hash", () => {
    expect(removeTokenFromUrl("/reset-password?token=abc123#section")).toBe("/reset-password#section");
  });

  it("preserves both an unrelated query parameter and a hash together", () => {
    expect(removeTokenFromUrl("/reset-password?lang=en&token=abc123#section")).toBe(
      "/reset-password?lang=en#section"
    );
  });

  it("never leaves the literal token value anywhere in the sanitized output", () => {
    const sanitized = removeTokenFromUrl("/reset-password?token=super-secret-value-123");
    expect(sanitized).not.toContain("super-secret-value-123");
    expect(sanitized).not.toContain("token");
  });

  it("is a no-op when there is no token to remove", () => {
    expect(removeTokenFromUrl("/reset-password")).toBe("/reset-password");
    expect(removeTokenFromUrl("/reset-password?lang=en")).toBe("/reset-password?lang=en");
  });

  it("never throws on malformed/edge input", () => {
    expect(() => removeTokenFromUrl("")).not.toThrow();
    expect(() => removeTokenFromUrl("not a url at all")).not.toThrow();
    expect(() => removeTokenFromUrl("/reset-password?token=a&token=b")).not.toThrow();
  });

  it("never touches localStorage or sessionStorage", () => {
    const localSpy = vi.spyOn(Storage.prototype, "setItem");
    removeTokenFromUrl("/reset-password?token=abc123");
    expect(localSpy).not.toHaveBeenCalled();
    localSpy.mockRestore();
  });
});
