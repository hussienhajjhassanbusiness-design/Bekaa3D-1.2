import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { customersApi } from "./customersApi";

vi.mock("@/lib/api/apiClient", () => ({
  apiClient: { get: vi.fn(), patch: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.patch).mockReset();
});

describe("customersApi.listUsers", () => {
  it("omits unset query parameters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await customersApi.listUsers({});
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/admin/users");
  });

  it("builds the exact confirmed query parameter names when set", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], next_cursor: null });
    await customersApi.listUsers({ search: "a@b.com", active: true, verified: false, cursor: "c1", limit: 50 });
    const [path] = vi.mocked(apiClient.get).mock.calls[0] as [string];
    expect(path).toContain("search=a%40b.com");
    expect(path).toContain("active=true");
    expect(path).toContain("verified=false");
    expect(path).toContain("cursor=c1");
    expect(path).toContain("limit=50");
  });
});

describe("customersApi.updateUserActive", () => {
  it("PATCHes only is_active, with CSRF", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      id: "u1",
      email: "a@b.com",
      role: "customer",
      is_active: false,
      email_verified_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });

    await customersApi.updateUserActive("u1", false);

    expect(apiClient.patch).toHaveBeenCalledWith(
      "/api/v1/admin/users/u1",
      { is_active: false },
      { csrf: true }
    );
  });
});
