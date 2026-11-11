import { describe, it, expect } from "vitest";
import { PROXY_MAX_BODY_BYTES } from "./proxyBodyLimit";
import { BYI_LIMITS } from "@/lib/byi/customRequestApi";
import nextConfig from "../../../next.config";

describe("proxy body limit", () => {
  it("lets the largest Bring Your Idea body through the /api proxy", () => {
    expect(PROXY_MAX_BODY_BYTES).toBe(BYI_LIMITS.maxAttachments * BYI_LIMITS.maxAttachmentBytes + 64 * 1024);
    expect(nextConfig.experimental?.proxyClientMaxBodySize).toBe(PROXY_MAX_BODY_BYTES);
  });
});
