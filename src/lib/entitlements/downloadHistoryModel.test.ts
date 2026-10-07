import { describe, it, expect } from "vitest";
import type { DownloadHistoryItem } from "./downloadHistoryModel";

// FVS-021-IMPLEMENTATION-PLAN.md T02 — #ARCHITECTURE-DOWNLOAD-HISTORY-ADAPTER.
// `dateLabel` is a presentation-ready string, never a raw Date/
// timestamp this file would format itself — timezone/display
// conversion rules are not defined by any governing document, so none
// are invented here; a future adapter decides how to render a
// confirmed timestamp field into this string.

describe("DownloadHistoryItem", () => {
  it("accepts only the normalized presentation fields this plan actually needs", () => {
    const item: DownloadHistoryItem = { id: "dl-1", productDisplayName: "Dragon STL", dateLabel: "Oct 7, 2026" };
    expect(item.id).toBe("dl-1");
  });

  it("has no raw timestamp/Date field — only a presentation-ready label", () => {
    const item: DownloadHistoryItem = { id: "dl-1", productDisplayName: "Dragon STL", dateLabel: "Oct 7, 2026" };
    expect("downloadedAt" in item).toBe(false);
    expect("timestamp" in item).toBe(false);
  });
});
