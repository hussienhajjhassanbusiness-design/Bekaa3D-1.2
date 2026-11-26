import { describe, it, expect } from "vitest";
import { buildProxyRewrites } from "./proxyRewrites";

describe("buildProxyRewrites", () => {
  it("registers nothing when no target is configured (clean checkout still builds)", () => {
    expect(buildProxyRewrites({ apiTarget: undefined, mediaTarget: undefined, nodeEnv: "development" })).toEqual([]);
  });

  it("registers the health rule before the general /api rule", () => {
    expect(
      buildProxyRewrites({ apiTarget: "http://localhost:8000", mediaTarget: undefined, nodeEnv: "development" })
    ).toEqual([
      { source: "/api/health/:path*", destination: "http://localhost:8000/health/:path*" },
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    ]);
  });

  it("adds the development-only /media rule when a media target is set outside production", () => {
    const rules = buildProxyRewrites({
      apiTarget: "http://localhost:8000",
      mediaTarget: "http://localhost:8001",
      nodeEnv: "development",
    });
    expect(rules).toContainEqual({ source: "/media/:path*", destination: "http://localhost:8001/:path*" });
    expect(rules.at(-1)).toEqual({ source: "/media/:path*", destination: "http://localhost:8001/:path*" });
  });

  it("never registers the /media rule in a production build (production URL semantics unchanged)", () => {
    const rules = buildProxyRewrites({
      apiTarget: "http://localhost:8000",
      mediaTarget: "http://localhost:8001",
      nodeEnv: "production",
    });
    expect(rules.some((rule) => rule.source.startsWith("/media"))).toBe(false);
  });
});
