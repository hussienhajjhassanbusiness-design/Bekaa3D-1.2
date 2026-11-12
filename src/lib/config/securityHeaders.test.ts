import { describe, it, expect } from "vitest";
import { buildContentSecurityPolicy, buildSecurityHeaders, TURNSTILE_ORIGIN } from "./securityHeaders";

const keys = (env: string) => buildSecurityHeaders({ nodeEnv: env }).map((h) => h.key);

describe("buildSecurityHeaders (phase 6F)", () => {
  it("always sends nosniff, referrer policy, frame denial and a permissions policy", () => {
    for (const env of ["development", "production"]) {
      expect(keys(env)).toEqual(expect.arrayContaining(["X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Permissions-Policy"]));
    }
  });

  it("sends the CSP only from a production build", () => {
    expect(keys("production")).toContain("Content-Security-Policy");
    expect(keys("development")).not.toContain("Content-Security-Policy");
    expect(keys("test")).not.toContain("Content-Security-Policy");
  });

  it("does not send HSTS (the TLS-terminating proxy owns it)", () => {
    expect(keys("production")).not.toContain("Strict-Transport-Security");
  });
});

describe("buildContentSecurityPolicy", () => {
  const csp = buildContentSecurityPolicy();
  const directive = (name: string) => csp.split("; ").find((d) => d.startsWith(`${name} `));

  it("allows Turnstile's script and iframe and nothing else third-party", () => {
    expect(directive("script-src")).toBe(`script-src 'self' 'unsafe-inline' ${TURNSTILE_ORIGIN}`);
    expect(directive("frame-src")).toBe(`frame-src ${TURNSTILE_ORIGIN}`);
    expect(directive("connect-src")).toBe("connect-src 'self'");
  });

  it("forbids framing, plugins, base-tag and cross-origin form tricks", () => {
    expect(directive("frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(directive("object-src")).toBe("object-src 'none'");
    expect(directive("base-uri")).toBe("base-uri 'self'");
    expect(directive("form-action")).toBe("form-action 'self'");
  });

  it("never allows eval", () => {
    expect(csp).not.toContain("unsafe-eval");
  });
});
