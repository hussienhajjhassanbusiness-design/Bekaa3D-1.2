import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";
import { settingsApi, settingsKeys } from "./settingsApi";
import { toEditableSetting, type RawSettingValue } from "./settingsAdapter";

export function useAdminSettingUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: RawSettingValue }) => settingsApi.updateSetting(key, value),
    onSuccess: (saved) => {
      // Backend applies a setting PATCH immediately and authoritatively
      // (AGENTS.md). Write the returned row into the cached list straight
      // away, so a form that just saved never flashes the pre-save value,
      // then refetch the canonical list anyway.
      queryClient.setQueryData<EditableSetting[]>(settingsKeys.list(), (current) =>
        current?.map((setting) => (setting.key === saved.key ? toEditableSetting(saved) : setting))
      );
      void queryClient.invalidateQueries({ queryKey: settingsKeys.list() });
    },
  });
}
