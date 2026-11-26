import { describe, it, expect } from "vitest";
import { resolveTurnstileSiteKey, TURNSTILE_TEST_SITE_KEY } from "./turnstileConfig";

describe("resolveTurnstileSiteKey", () => {
  it("uses the configured public site key when set", () => {
    expect(resolveTurnstileSiteKey({ siteKey: "0x4AAAAAAAreal", nodeEnv: "production" })).toBe("0x4AAAAAAAreal");
    expect(resolveTurnstileSiteKey({ siteKey: "0x4AAAAAAAreal", nodeEnv: "development" })).toBe("0x4AAAAAAAreal");
  });

  it("falls back to Cloudflare's public always-pass test key outside production", () => {
    expect(TURNSTILE_TEST_SITE_KEY).toBe("1x00000000000000000000AA");
    expect(resolveTurnstileSiteKey({ siteKey: undefined, nodeEnv: "development" })).toBe(TURNSTILE_TEST_SITE_KEY);
    expect(resolveTurnstileSiteKey({ siteKey: "", nodeEnv: "test" })).toBe(TURNSTILE_TEST_SITE_KEY);
  });

  it("never falls back to the test key in production", () => {
    expect(resolveTurnstileSiteKey({ siteKey: undefined, nodeEnv: "production" })).toBeNull();
    expect(resolveTurnstileSiteKey({ siteKey: "  ", nodeEnv: "production" })).toBeNull();
  });
});
