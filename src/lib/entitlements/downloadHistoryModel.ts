// #ARCHITECTURE-DOWNLOAD-HISTORY-ADAPTER
//
// Frontend-normalized presentation model ONLY — NOT a claim about the
// real `GET /api/v1/me/downloads` response field names
// (FVS-021-IMPLEMENTATION-PLAN.md §1). `dateLabel` is deliberately a
// presentation-ready string, not a raw Date/timestamp this model
// formats itself — no governing document defines timezone/display
// conversion rules, so none are invented here; a future adapter
// decides how to render a confirmed timestamp field into this string.
export interface DownloadHistoryItem {
  id: string;
  productDisplayName: string;
  dateLabel: string;
}
