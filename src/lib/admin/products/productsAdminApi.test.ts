import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { productsAdminApi } from "./productsAdminApi";

vi.mock("@/lib/api/apiClient", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.post).mockReset();
  vi.mocked(apiClient.patch).mockReset();
  vi.mocked(apiClient.del).mockReset();
});

describe("productsAdminApi.listProducts", () => {
  it("omits unset parameters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await productsAdminApi.listProducts({});
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/admin/products");
  });

  it("builds every confirmed query parameter when set", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await productsAdminApi.listProducts({ type: "stl", q: "vase", sort: "-price", cursor: "c1", limit: 10 });
    const [path] = vi.mocked(apiClient.get).mock.calls[0] as [string];
    expect(path).toContain("type=stl");
    expect(path).toContain("q=vase");
    expect(path).toContain("sort=-price");
    expect(path).toContain("cursor=c1");
    expect(path).toContain("limit=10");
  });
});

describe("productsAdminApi.deleteProduct", () => {
  it("sends version as a query parameter, with CSRF, never in the body", async () => {
    vi.mocked(apiClient.del).mockResolvedValue(undefined);
    await productsAdminApi.deleteProduct("p1", 3);
    expect(apiClient.del).toHaveBeenCalledWith("/api/v1/admin/products/p1", { csrf: true, query: { version: 3 } });
  });
});

describe("productsAdminApi.createProduct / updateProduct", () => {
  it("POSTs the body with CSRF", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    await productsAdminApi.createProduct({ type: "physical" });
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/admin/products", { type: "physical" }, { csrf: true });
  });

  it("PATCHes the body with CSRF", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({});
    await productsAdminApi.updateProduct("p1", { version: 2 });
    expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/admin/products/p1", { version: 2 }, { csrf: true });
  });
});
