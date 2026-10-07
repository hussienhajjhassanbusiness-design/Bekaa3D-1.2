"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { EntitlementCard } from "./EntitlementCard";
import type { EntitlementModel } from "@/lib/entitlements/entitlementModel";

export interface EntitlementListProps {
  entitlements: readonly EntitlementModel[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onBrowseShop?: () => void;
  renderActionSlot?: (entitlement: EntitlementModel) => ReactNode;
}

const EMPTY_MESSAGE = "You don't own any STL products yet.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your library. Please try again.";

// #FVS020-ENTITLEMENT-LIST
//
// Presentational only — no network, no query. There is deliberately no
// revoked badge/branch/filter anywhere in this component: VS-017's own
// rule excludes revoked entitlements from the list endpoint entirely,
// so there is nothing for this presentation layer to hide — a future
// API adapter simply renders whatever the active-entitlements endpoint
// returns. `renderActionSlot` is the seam FVS-021 populates with its
// own `DownloadButton` per entitlement.
export function EntitlementList({
  entitlements,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  onBrowseShop,
  renderActionSlot,
}: EntitlementListProps) {
  if (isLoading) {
    return (
      <div role="status">
        <span className="sr-only">Loading your library…</span>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="mt-2 h-16 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={errorMessage ?? DEFAULT_ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (entitlements.length === 0) {
    return <EmptyState message={EMPTY_MESSAGE} actionLabel="Browse the shop" onAction={onBrowseShop} />;
  }

  return (
    <ul className="grid grid-cols-1 gap-4 tablet:grid-cols-2 desktop:grid-cols-3">
      {entitlements.map((entitlement) => (
        <li key={entitlement.id}>
          <EntitlementCard entitlement={entitlement} actionSlot={renderActionSlot?.(entitlement)} />
        </li>
      ))}
    </ul>
  );
}
