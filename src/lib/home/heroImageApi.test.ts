import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { describeHeroImageError, heroImageApi } from "./heroImageApi";

vi.mock("@/lib/api/apiClient", () => ({ apiClient: { get: vi.fn(), putForm: vi.fn() } }));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.putForm).mockReset();
});

describe("heroImageApi", () => {
  it("reads the public hero image", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ url: null });
    expect(await heroImageApi.getHeroImage()).toEqual({ url: null });
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/home/hero-image");
  });

  it("replaces it with a multipart PUT carrying only the file, with CSRF", async () => {
    vi.mocked(apiClient.putForm).mockResolvedValue({ url: "/media/home/hero/x.png" });
    const file = new File(["x"], "hero.png", { type: "image/png" });

    expect(await heroImageApi.replaceHeroImage(file)).toEqual({ url: "/media/home/hero/x.png" });
    const [path, formData, options] = vi.mocked(apiClient.putForm).mock.calls[0] as [string, FormData, object];
    expect(path).toBe("/api/v1/admin/home/hero-image");
    expect([...formData.keys()]).toEqual(["file"]);
    expect(formData.get("file")).toBe(file);
    expect(options).toEqual({ csrf: true });
  });
});

describe("describeHeroImageError", () => {
  it.each([
    [{ kind: "http", status: 422, code: "UPLOAD_REJECTED" }, "at least 400 × 400 px"],
    [{ kind: "http", status: 422, code: "MALWARE_DETECTED" }, "security scan"],
    [{ kind: "http", status: 503, code: "SERVICE_UNAVAILABLE" }, "temporarily unavailable"],
    [{ kind: "network" }, "couldn't reach the server"],
  ])("explains %o and says the saved image is unchanged", (error, text) => {
    const message = describeHeroImageError(error);
    expect(message).toContain(text);
    expect(message).toMatch(/Your current hero image is unchanged\.$/);
  });

  it("never echoes the server's detail text", () => {
    const message = describeHeroImageError({ kind: "http", code: "UPLOAD_REJECTED", detail: "<script>x</script>" });
    expect(message).not.toContain("script");
  });
});
