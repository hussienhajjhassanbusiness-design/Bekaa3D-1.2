import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { referenceDataAdminApi } from "./referenceDataAdminApi";

vi.mock("@/lib/api/apiClient", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.post).mockReset();
  vi.mocked(apiClient.patch).mockReset();
  vi.mocked(apiClient.del).mockReset();
});

describe("referenceDataAdminApi.list", () => {
  it("requests the resource's own path with include_deleted when asked", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await referenceDataAdminApi.list("categories", true);
    const [path] = vi.mocked(apiClient.get).mock.calls[0] as [string];
    expect(path).toBe("/api/v1/admin/categories?limit=100&include_deleted=true");
  });

  it("omits include_deleted when false", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await referenceDataAdminApi.list("materials", false);
    const [path] = vi.mocked(apiClient.get).mock.calls[0] as [string];
    expect(path).toBe("/api/v1/admin/materials?limit=100");
  });
});

describe("referenceDataAdminApi.create", () => {
  it("sends name and slug for categories", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "c1",
      name: "Toys",
      slug: "toys",
      is_active: true,
      deleted_at: null,
      created_at: "x",
      updated_at: "x",
    });

    await referenceDataAdminApi.create("categories", { name: "Toys", slug: "toys" });

    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/admin/categories", { name: "Toys", slug: "toys" }, { csrf: true });
  });

  it("never sends a slug field for materials/colours", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "m1",
      name: "PLA",
      is_active: true,
      deleted_at: null,
      created_at: "x",
      updated_at: "x",
    });

    await referenceDataAdminApi.create("materials", { name: "PLA", slug: "should-not-be-sent" });

    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/admin/materials", { name: "PLA" }, { csrf: true });
  });
});

describe("referenceDataAdminApi.update", () => {
  it("PATCHes only the provided fields", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      id: "c1",
      name: "Toys",
      slug: "toys",
      is_active: false,
      deleted_at: null,
      created_at: "x",
      updated_at: "x",
    });

    await referenceDataAdminApi.update("categories", "c1", { isActive: false });

    expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/admin/categories/c1", { is_active: false }, { csrf: true });
  });
});

describe("referenceDataAdminApi.archive", () => {
  it("DELETEs with CSRF and returns nothing", async () => {
    vi.mocked(apiClient.del).mockResolvedValue(undefined);
    await referenceDataAdminApi.archive("colours", "co1");
    expect(apiClient.del).toHaveBeenCalledWith("/api/v1/admin/colours/co1", { csrf: true });
  });
});
