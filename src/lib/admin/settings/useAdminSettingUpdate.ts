import { useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi, settingsKeys } from "./settingsApi";
import type { RawSettingValue } from "./settingsAdapter";

export function useAdminSettingUpdate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: RawSettingValue }) => settingsApi.updateSetting(key, value),
    onSuccess: () => {
      // Backend applies a setting PATCH immediately and authoritatively
      // (AGENTS.md) — refetch the canonical list rather than optimistically
      // patch the cache, so the row reflects exactly what the server now
      // has stored.
      void queryClient.invalidateQueries({ queryKey: settingsKeys.list() });
    },
  });
}
