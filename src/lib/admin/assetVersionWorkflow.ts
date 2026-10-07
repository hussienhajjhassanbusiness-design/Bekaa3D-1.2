import type { StatusBadgeTone } from "@/components/admin/StatusBadge";

// #ARCHITECTURE-ASSET-VERSION-ADAPTER
//
// Frontend-normalized model only — NOT a claim about VS-016's real
// response field names (still NEEDS BACKEND CONFIRMATION,
// FVS-018-IMPLEMENTATION-PLAN.md §1). "pending"/"clean"/"infected" and
// "current"/"superseded"/"pending" mirror FVS-018's own capability line
// verbatim — not invented vocabulary. A future API adapter maps the
// real backend DTOs onto this shape; this model deliberately omits any
// storage URL/path/hash field, since none of that is a confirmed-safe
// frontend concern.
export type ScanStatus = "pending" | "clean" | "infected";

export interface AssetFile {
  id: string;
  displayName: string;
  scanStatus: ScanStatus;
}

export type AssetVersionState = "current" | "superseded" | "pending";

export interface AssetVersion {
  id: string;
  label: string;
  files: readonly AssetFile[];
  state: AssetVersionState;
}

// #SECURITY-ASSET-PUBLISH-GATE
//
// UI gating ONLY. The backend MUST independently enforce the same
// all-clean rule before actually marking a version current — disabling
// this button client-side is a UX courtesy, never the real security
// boundary (vertical-slice-plan.md VS-016: "cannot publish until
// clean" is a server-side invariant).
//
// An empty file list is deliberately NOT "all clean" — `[].every(...)`
// vacuously returns true, which would make a bundle with zero files
// publishable. That is never correct.
export function areAllAssetFilesClean(files: readonly AssetFile[]): boolean {
  return files.length > 0 && files.every((file) => file.scanStatus === "clean");
}

export function hasPendingAssetFiles(files: readonly AssetFile[]): boolean {
  return files.some((file) => file.scanStatus === "pending");
}

export function hasInfectedAssetFiles(files: readonly AssetFile[]): boolean {
  return files.some((file) => file.scanStatus === "infected");
}

// Infected takes priority over pending in the reason text: a bundle
// that has both an infected file and a still-scanning file is blocked
// for the more serious reason, not left looking like "just wait."
export function getPublishBlockedReason(files: readonly AssetFile[]): string | null {
  if (files.length === 0) {
    return "This version has no files to publish.";
  }
  if (hasInfectedAssetFiles(files)) {
    return "This version contains an infected file and cannot be published.";
  }
  if (hasPendingAssetFiles(files)) {
    return "Waiting for scan to complete.";
  }
  if (!areAllAssetFilesClean(files)) {
    return "This version cannot be published yet.";
  }
  return null;
}

const SCAN_STATUS_DESCRIPTIONS: Record<ScanStatus, { label: string; tone: StatusBadgeTone }> = {
  pending: { label: "Pending scan", tone: "warning" },
  clean: { label: "Clean", tone: "positive" },
  infected: { label: "Infected", tone: "negative" },
};

export function describeScanStatus(status: ScanStatus): { label: string; tone: StatusBadgeTone } {
  return SCAN_STATUS_DESCRIPTIONS[status];
}

const VERSION_STATE_DESCRIPTIONS: Record<AssetVersionState, { label: string; tone: StatusBadgeTone }> = {
  current: { label: "Current", tone: "positive" },
  superseded: { label: "Superseded", tone: "neutral" },
  pending: { label: "Not yet published", tone: "warning" },
};

export function describeAssetVersionState(state: AssetVersionState): { label: string; tone: StatusBadgeTone } {
  return VERSION_STATE_DESCRIPTIONS[state];
}

// A single, derived-from-current-props summary string — rendered inside
// an aria-live region, it re-announces naturally whenever its text
// content changes across a re-render (e.g. after a poll resolves a
// file from pending to clean), without this module needing to track
// "what changed" itself.
export function summarizeScanStatuses(files: readonly AssetFile[]): string {
  const counts = { pending: 0, clean: 0, infected: 0 };
  for (const file of files) {
    counts[file.scanStatus] += 1;
  }
  const parts: string[] = [];
  if (counts.clean > 0) parts.push(`${counts.clean} clean`);
  if (counts.pending > 0) parts.push(`${counts.pending} pending`);
  if (counts.infected > 0) parts.push(`${counts.infected} infected`);
  return parts.length > 0 ? parts.join(", ") : "No files.";
}
