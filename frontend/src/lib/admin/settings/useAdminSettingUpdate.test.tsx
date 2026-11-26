import { describe, it, expect, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";
import { useAdminSettingUpdate } from "./useAdminSettingUpdate";
import { settingsApi, settingsKeys } from "./settingsApi";
import type { RawSettingRead } from "./settingsAdapter";

vi.mock("./settingsApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./settingsApi")>();
  return { ...actual, settingsApi: { ...actual.settingsApi, updateSetting: vi.fn() } };
});

const SAVED: RawSettingRead = {
  key: "pickup_hours",
  type: "string",
  value: "10-6",
  description: null,
  unit: null,
  minimum: null,
  maximum: null,
  nullable: true,
  is_public: true,
  updated_at: "2026-11-24T00:00:00Z",
  updated_by: null,
};

describe("useAdminSettingUpdate", () => {
  it("writes the server's saved row into the cached list, leaving other rows alone", async () => {
    vi.mocked(settingsApi.updateSetting).mockResolvedValue(SAVED);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const other: EditableSetting = { key: "accepting_orders", type: "boolean", label: "Accepting orders", value: true };
    queryClient.setQueryData<EditableSetting[]>(settingsKeys.list(), [
      other,
      { key: "pickup_hours", type: "string", label: "Pickup hours", value: "9-5" },
    ]);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useAdminSettingUpdate(), { wrapper });

    await act(() => result.current.mutateAsync({ key: "pickup_hours", value: "10-6" }));

    expect(settingsApi.updateSetting).toHaveBeenCalledWith("pickup_hours", "10-6");
    const cached = queryClient.getQueryData<EditableSetting[]>(settingsKeys.list());
    expect(cached?.[0]).toBe(other);
    expect(cached?.[1]).toMatchObject({ key: "pickup_hours", value: "10-6" });
  });
});
