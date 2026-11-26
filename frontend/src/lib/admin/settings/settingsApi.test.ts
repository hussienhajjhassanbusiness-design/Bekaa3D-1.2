import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { settingsApi } from "./settingsApi";

vi.mock("@/lib/api/apiClient", () => ({
  apiClient: { get: vi.fn(), patch: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.patch).mockReset();
});

// openapi.json: `PATCH /api/v1/admin/settings/{key}`, body `SettingUpdate`
// (`{ value }` only, extra fields forbidden), admin + MFA + X-CSRF-Token.
describe("settingsApi.updateSetting", () => {
  it("PATCHes one key with a { value }-only body and CSRF", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ key: "pickup_hours", value: "9-5" });

    await settingsApi.updateSetting("pickup_hours", "9-5");

    expect(apiClient.patch).toHaveBeenCalledTimes(1);
    expect(apiClient.patch).toHaveBeenCalledWith(
      "/api/v1/admin/settings/pickup_hours",
      { value: "9-5" },
      { csrf: true }
    );
  });
});

describe("settingsApi.listAllSettings", () => {
  it("walks every cursor page and flattens the items", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ items: [{ key: "a" }], next_cursor: "c1" })
      .mockResolvedValueOnce({ items: [{ key: "b" }], next_cursor: null });

    const items = await settingsApi.listAllSettings();

    expect(items.map((item) => item.key)).toEqual(["a", "b"]);
    expect(vi.mocked(apiClient.get).mock.calls[1]?.[0]).toBe("/api/v1/admin/settings?limit=100&cursor=c1");
  });
});
