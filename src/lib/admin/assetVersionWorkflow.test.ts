import { describe, it, expect } from "vitest";
import {
  areAllAssetFilesClean,
  hasPendingAssetFiles,
  hasInfectedAssetFiles,
  getPublishBlockedReason,
  describeScanStatus,
  describeAssetVersionState,
  summarizeScanStatuses,
  type AssetFile,
} from "./assetVersionWorkflow";

// FVS-018-IMPLEMENTATION-PLAN.md T01 — "pending"/"clean"/"infected" and
// "current"/"superseded"/"pending" are frontend-normalized concepts
// mirroring FVS-018's own capability line, never claimed backend enum
// literals (plan §1). These helpers are UI gating ONLY — the backend
// MUST independently enforce the same all-clean rule
// (#SECURITY-ASSET-PUBLISH-GATE); the frontend disabling a button is
// never treated as the real security boundary.

function file(scanStatus: AssetFile["scanStatus"], id = "f1"): AssetFile {
  return { id, displayName: `${id}.stl`, scanStatus };
}

describe("hasPendingAssetFiles / hasInfectedAssetFiles / areAllAssetFilesClean", () => {
  it("treats an empty file list as NOT publishable (no all-clean on vacuous truth)", () => {
    expect(areAllAssetFilesClean([])).toBe(false);
    expect(hasPendingAssetFiles([])).toBe(false);
    expect(hasInfectedAssetFiles([])).toBe(false);
  });

  it("is all-clean when every file is clean", () => {
    const files = [file("clean", "a"), file("clean", "b")];
    expect(areAllAssetFilesClean(files)).toBe(true);
    expect(hasPendingAssetFiles(files)).toBe(false);
    expect(hasInfectedAssetFiles(files)).toBe(false);
  });

  it("flags pending when at least one file is pending", () => {
    const files = [file("clean", "a"), file("pending", "b")];
    expect(hasPendingAssetFiles(files)).toBe(true);
    expect(areAllAssetFilesClean(files)).toBe(false);
  });

  it("flags infected when at least one file is infected", () => {
    const files = [file("clean", "a"), file("infected", "b")];
    expect(hasInfectedAssetFiles(files)).toBe(true);
    expect(areAllAssetFilesClean(files)).toBe(false);
  });

  it("flags both pending and infected for a mixed bundle, and is never all-clean", () => {
    const files = [file("pending", "a"), file("infected", "b"), file("clean", "c")];
    expect(hasPendingAssetFiles(files)).toBe(true);
    expect(hasInfectedAssetFiles(files)).toBe(true);
    expect(areAllAssetFilesClean(files)).toBe(false);
  });
});

describe("getPublishBlockedReason", () => {
  it("returns null (eligible) when all files are clean and non-empty", () => {
    expect(getPublishBlockedReason([file("clean")])).toBeNull();
  });

  it("returns a safe reason for an empty bundle", () => {
    expect(getPublishBlockedReason([])).not.toBeNull();
  });

  it("returns a safe reason when any file is pending", () => {
    expect(getPublishBlockedReason([file("clean", "a"), file("pending", "b")])).toMatch(/scan/i);
  });

  it("returns a safe reason when any file is infected, taking priority over pending wording", () => {
    const reason = getPublishBlockedReason([file("pending", "a"), file("infected", "b")]);
    expect(reason).toMatch(/infected/i);
  });
});

describe("describeScanStatus", () => {
  it("gives each scan status a human-readable label", () => {
    expect(describeScanStatus("pending").label).toBe("Pending scan");
    expect(describeScanStatus("clean").label).toBe("Clean");
    expect(describeScanStatus("infected").label).toBe("Infected");
  });

  it("gives each scan status a bounded tone", () => {
    for (const status of ["pending", "clean", "infected"] as const) {
      expect(["neutral", "positive", "negative", "warning"]).toContain(describeScanStatus(status).tone);
    }
  });
});

describe("describeAssetVersionState", () => {
  it("gives each version state a human-readable label", () => {
    expect(describeAssetVersionState("current").label).toBe("Current");
    expect(describeAssetVersionState("superseded").label).toBe("Superseded");
    expect(describeAssetVersionState("pending").label).toBe("Not yet published");
  });
});

describe("summarizeScanStatuses", () => {
  it("counts each scan status by name", () => {
    const summary = summarizeScanStatuses([file("clean", "a"), file("pending", "b"), file("clean", "c")]);
    expect(summary).toMatch(/2 clean/i);
    expect(summary).toMatch(/1 pending/i);
  });

  it("gives a safe summary for an empty bundle", () => {
    expect(summarizeScanStatuses([])).toBe("No files.");
  });
});
