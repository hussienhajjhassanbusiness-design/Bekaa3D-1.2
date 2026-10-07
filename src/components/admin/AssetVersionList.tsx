"use client";

import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { StatusBadge } from "./StatusBadge";
import {
  describeScanStatus,
  describeAssetVersionState,
  getPublishBlockedReason,
  summarizeScanStatuses,
  type AssetVersion,
} from "@/lib/admin/assetVersionWorkflow";

export interface AssetVersionListProps {
  versions: readonly AssetVersion[];
  onPublish: (versionId: string) => void;
  isPublishing?: boolean;
}

// #FVS018-ASSET-VERSION-LIST
//
// Presentational only — no network. Publish is disabled (not merely
// discouraged) per the pure #SECURITY-ASSET-PUBLISH-GATE helpers; the
// backend remains the real authority. `onPublish` never optimistically
// marks a version current here — this component only renders whatever
// `versions`/`state` the parent (eventually server state) supplies.
// Current/superseded/pending-publish state and per-file scan status
// both reuse the generalized `StatusBadge` (ScanStatusBadge, T02, is
// absorbed here — no separate wrapper component).
export function AssetVersionList({ versions, onPublish, isPublishing = false }: AssetVersionListProps) {
  return (
    <ul>
      {versions.map((version) => (
        <VersionRow key={version.id} version={version} onPublish={onPublish} isPublishing={isPublishing} />
      ))}
    </ul>
  );
}

function VersionRow({
  version,
  onPublish,
  isPublishing,
}: {
  version: AssetVersion;
  onPublish: (versionId: string) => void;
  isPublishing: boolean;
}) {
  const reasonId = useId();
  const stateDescriptor = describeAssetVersionState(version.state);
  const blockedReason = version.state === "pending" ? getPublishBlockedReason(version.files) : null;

  return (
    <li className="border-b border-border-default py-4">
      <div className="flex items-center gap-2">
        <span className="text-body font-semibold text-text-primary">{version.label}</span>
        <StatusBadge label={stateDescriptor.label} tone={stateDescriptor.tone} />
      </div>

      {/* Announces naturally whenever this text changes across a
          re-render (e.g. a poll resolving pending -> clean) — not a
          per-badge live region, which would spam repeated
          announcements for every file individually. */}
      <div role="status" aria-live="polite" className="sr-only">
        {summarizeScanStatuses(version.files)}
      </div>

      <ul className="mt-2">
        {version.files.map((file) => {
          const fileDescriptor = describeScanStatus(file.scanStatus);
          return (
            <li key={file.id} className="flex items-center gap-2 py-1">
              <span className="text-body text-text-primary">{file.displayName}</span>
              <StatusBadge label={fileDescriptor.label} tone={fileDescriptor.tone} />
            </li>
          );
        })}
      </ul>

      {version.state === "pending" && (
        <div className="mt-2">
          <Button
            type="button"
            onClick={() => onPublish(version.id)}
            disabled={blockedReason !== null || isPublishing}
            isLoading={isPublishing}
            aria-describedby={blockedReason ? reasonId : undefined}
          >
            Publish
          </Button>
          {blockedReason && (
            <p id={reasonId} className="mt-1 text-caption text-text-secondary">
              {blockedReason}
            </p>
          )}
        </div>
      )}
    </li>
  );
}
