import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { RawSettingPage, RawSettingRead, RawSettingValue } from "./settingsAdapter";

// P1-3 (docs/backend-handoff/BACKEND-RESPONSE.md) — GET is cursor-
// paginated (C2) like every admin list, but the settings screen renders
// one flat list, never a "load more" control: the real registry is a
// small, fixed set of keys (well under one page at the max limit), so
// this walks every page internally and returns the flattened result —
// no admin-visible pagination UI for this one screen.
async function listAllSettings(): Promise<RawSettingRead[]> {
  const items: RawSettingRead[] = [];
  let cursor: string | undefined;

  do {
    const path = cursor
      ? `/api/v1/admin/settings?limit=100&cursor=${encodeURIComponent(cursor)}`
      : "/api/v1/admin/settings?limit=100";
    const page = await adminRequest(() => apiClient.get<RawSettingPage>(path));
    items.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);

  return items;
}

async function updateSetting(key: string, value: RawSettingValue): Promise<RawSettingRead> {
  return adminRequest(() =>
    apiClient.patch<RawSettingRead>(`/api/v1/admin/settings/${encodeURIComponent(key)}`, { value }, { csrf: true })
  );
}

export const settingsApi = { listAllSettings, updateSetting };

export const settingsKeys = {
  root: ["admin", "settings"] as const,
  list: () => [...settingsKeys.root, "list"] as const,
};
