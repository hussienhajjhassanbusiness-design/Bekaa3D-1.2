import { useQuery } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";
import { settingsApi, settingsKeys } from "./settingsApi";
import { toEditableSettings } from "./settingsAdapter";

export function useAdminSettings() {
  return useQuery<EditableSetting[], ApiError>({
    queryKey: settingsKeys.list(),
    queryFn: async () => toEditableSettings({ items: await settingsApi.listAllSettings(), next_cursor: null }),
  });
}
