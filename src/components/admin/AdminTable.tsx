"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";
import { Icon } from "@/components/ui/Icon";

export interface AdminTableColumn<T> {
  header: string;
  render: (row: T) => ReactNode;
}

export interface AdminTableProps<T> {
  columns: readonly AdminTableColumn<T>[];
  rows: readonly T[];
  getRowKey: (row: T) => string;
  isLoading?: boolean;
  emptyMessage?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchLabel?: string;
  hasPrevious?: boolean;
  hasNext?: boolean;
  onPrevious?: () => void;
  onNext?: () => void;
  rowActions?: (row: T) => ReactNode;
}

const DEFAULT_EMPTY_MESSAGE = "No results found.";

// #SHARED-ADMIN-TABLE
//
// Generic table shell reused by every later admin list (orders, offers,
// reviews, BYI, audit log) — intentionally carries zero customer-specific
// knowledge. Search/pagination are presentational-only controlled seams:
// this component never fetches, never persists, and never infers a total
// page count (callers decide hasPrevious/hasNext from their own data,
// since the real pagination shape is still NEEDS BACKEND CONFIRMATION for
// FVS-009 itself — see FVS-009-IMPLEMENTATION-PLAN.md §1).
//
// No sorting seam: the governing plans mention "sorting" exactly once, in
// a test-summary line only, with no capability/backend evidence anywhere
// else (plan §0) — adding one here would silently encode an unconfirmed
// requirement, so it is omitted.
//
// Responsive behavior is a horizontal-scroll wrapper, never a mobile-card
// fallback — admin tables must not drop identity/security columns based
// on viewport width.
//
// Redesign Batch 9 (COMPONENT-SPECS §43, §63 in-card bar, §49, §50;
// DESIGN-SYSTEM §12.16): one white card — optional in-card search bar, the
// table in its own horizontal-scroll region (focusable, named, so keyboard
// users can scroll it; the page itself never overflows), mono uppercase
// headers on lavender, px-6 py-4 cells, hairline row dividers and hover, and
// a footer with outline Previous / Next (cursor paging; no page numbers or
// totals, which the backend does not provide). Skeleton rows while loading;
// a §49 empty state. Columns are never dropped on small screens.
export function AdminTable<T>({
  columns,
  rows,
  getRowKey,
  isLoading = false,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  searchValue,
  onSearchChange,
  searchLabel = "Search",
  hasPrevious = false,
  hasNext = false,
  onPrevious,
  onNext,
  rowActions,
}: AdminTableProps<T>) {
  return (
    <div className="overflow-hidden rounded-card border border-outline-variant/40 bg-surface-container-lowest shadow-sm">
      {onSearchChange && (
        <div className="border-b border-outline-variant/40 p-4 tablet:px-6">
          <div className="max-w-md">
            <TextField
              label={searchLabel}
              value={searchValue ?? ""}
              onChange={(event) => onSearchChange(event.target.value)}
            />
          </div>
        </div>
      )}

      {isLoading ? (
        <div role="status" className="flex flex-col gap-3 p-4 tablet:p-6">
          <span className="sr-only">Loading…</span>
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              aria-hidden="true"
              className="h-10 animate-pulse rounded-control bg-surface-container-low motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center px-6 py-12 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-container text-on-surface-variant">
            <Icon name="search" className="h-7 w-7" />
          </span>
          <p className="mt-4 max-w-md font-body text-body-md text-on-surface-variant">{emptyMessage}</p>
        </div>
      ) : (
        <div
          role="region"
          aria-label="Results"
          tabIndex={0}
          className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
        >
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-outline-variant/40 bg-surface-container-low">
                {columns.map((column) => (
                  <th
                    key={column.header}
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 font-label text-label-sm uppercase text-on-surface-variant xl:px-6 xl:py-4"
                  >
                    {column.header}
                  </th>
                ))}
                {rowActions && (
                  <th scope="col" className="px-4 py-3 xl:px-6 xl:py-4">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/30">
              {rows.map((row) => {
                const key = getRowKey(row);
                return (
                  <tr
                    key={key}
                    className="transition-colors duration-200 hover:bg-surface-container-low/60 motion-reduce:transition-none"
                  >
                    {columns.map((column) => (
                      <td
                        key={column.header}
                        className="break-words px-4 py-3 align-top font-body text-body-md text-on-surface xl:px-6 xl:py-4"
                      >
                        {column.render(row)}
                      </td>
                    ))}
                    {rowActions && (
                      <td className="px-4 py-3 text-right align-top xl:px-6 xl:py-4">{rowActions(row)}</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(onPrevious || onNext) && (
        <div className="flex items-center justify-between gap-2 border-t border-outline-variant/40 px-4 py-3 tablet:px-6">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11"
            onClick={onPrevious}
            disabled={!hasPrevious}
          >
            <Icon name="arrow-back" className="h-4 w-4" />
            Previous
          </Button>
          <Button type="button" variant="outline" size="sm" className="min-h-11" onClick={onNext} disabled={!hasNext}>
            Next
            <Icon name="arrow-forward" className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
