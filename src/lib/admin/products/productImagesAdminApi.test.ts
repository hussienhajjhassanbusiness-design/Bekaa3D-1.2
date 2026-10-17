import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { productImagesAdminApi } from "./productImagesAdminApi";

vi.mock("@/lib/api/apiClient", () => ({
  apiClient: { post: vi.fn(), postForm: vi.fn(), patch: vi.fn(), put: vi.fn(), del: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.postForm).mockReset();
  vi.mocked(apiClient.patch).mockReset();
  vi.mocked(apiClient.put).mockReset();
  vi.mocked(apiClient.del).mockReset();
});

describe("productImagesAdminApi.uploadImage", () => {
  it("uploads as multipart/form-data with the file and optional alt_text", async () => {
    vi.mocked(apiClient.postForm).mockResolvedValue({});
    const file = new File(["x"], "photo.png", { type: "image/png" });
    await productImagesAdminApi.uploadImage("p1", file, "Front view");

    const [path, formData, options] = vi.mocked(apiClient.postForm).mock.calls[0] as [string, FormData, { csrf: boolean }];
    expect(path).toBe("/api/v1/admin/products/p1/images");
    expect(formData.get("file")).toBe(file);
    expect(formData.get("alt_text")).toBe("Front view");
    expect(options.csrf).toBe(true);
  });

  it("omits alt_text entirely when not provided", async () => {
    vi.mocked(apiClient.postForm).mockResolvedValue({});
    const file = new File(["x"], "photo.png", { type: "image/png" });
    await productImagesAdminApi.uploadImage("p1", file);

    const [, formData] = vi.mocked(apiClient.postForm).mock.calls[0] as [string, FormData];
    expect(formData.has("alt_text")).toBe(false);
  });
});

describe("productImagesAdminApi.updateAltText", () => {
  it("PATCHes alt_text, sending explicit null to clear it", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({});
    await productImagesAdminApi.updateAltText("p1", "i1", null);
    expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/admin/products/p1/images/i1", { alt_text: null }, { csrf: true });
  });
});

describe("productImagesAdminApi.setCover", () => {
  it("uses PUT, not PATCH, per the confirmed contract", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({});
    await productImagesAdminApi.setCover("p1", "i1");
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/admin/products/p1/images/i1/cover", undefined, { csrf: true });
  });
});

describe("productImagesAdminApi.reorder", () => {
  it("uses PUT with image_ids and returns the items array", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ items: [{ id: "i1" }] });
    const result = await productImagesAdminApi.reorder("p1", ["i2", "i1"]);
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/admin/products/p1/images/order", { image_ids: ["i2", "i1"] }, { csrf: true });
    expect(result).toEqual([{ id: "i1" }]);
  });
});

describe("productImagesAdminApi.deleteImage", () => {
  it("DELETEs with CSRF", async () => {
    vi.mocked(apiClient.del).mockResolvedValue(undefined);
    await productImagesAdminApi.deleteImage("p1", "i1");
    expect(apiClient.del).toHaveBeenCalledWith("/api/v1/admin/products/p1/images/i1", { csrf: true });
  });
});
