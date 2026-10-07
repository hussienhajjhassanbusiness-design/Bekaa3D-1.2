"use client";

import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import type { DownloadHistoryItem } from "@/lib/entitlements/downloadHistoryModel";

export interface DownloadHistoryTableProps {
  items: readonly DownloadHistoryItem[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
}

const EMPTY_MESSAGE = "You haven't downloaded anything yet.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your download history. Please try again.";

// #FVS021-DOWNLOAD-HISTORY-TABLE
//
// Presentational only — no network, no query. Desktop/tablet renders a
// real <table>; mobile renders a stacked list — both exist in markup
// simultaneously with CSS-only (`hidden`/`tablet:table`,
// `tablet:hidden`) visibility switching, no JS viewport detection.
// Whichever one is CSS `display:none` is automatically excluded from
// the accessibility tree, so there is no duplicate screen-reader
// announcement despite the dual markup. No pagination control is
// fabricated — whether history is paginated is unconfirmed
// (FVS-021-IMPLEMENTATION-PLAN.md §1).
export function DownloadHistoryTable({ items, isLoading = false, isError = false, errorMessage, onRetry }: DownloadHistoryTableProps) {
  if (isLoading) {
    return (
      <div role="status">
        <span className="sr-only">Loading your download history…</span>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="mt-2 h-10 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
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

  if (items.length === 0) {
    return <EmptyState message={EMPTY_MESSAGE} />;
  }

  return (
    <>
      <table className="hidden w-full text-left tablet:table">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
              Product
            </th>
            <th scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
              Downloaded
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="px-3 py-2 text-body text-text-primary">{item.productDisplayName}</td>
              <td className="px-3 py-2 text-body text-text-primary">{item.dateLabel}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="tablet:hidden">
        {items.map((item) => (
          <li key={item.id} className="border-b border-border-default py-3">
            <p className="text-body font-semibold text-text-primary">{item.productDisplayName}</p>
            <p className="mt-1 text-caption text-text-secondary">{item.dateLabel}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
