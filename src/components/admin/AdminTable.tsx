"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { TextField } from "@/components/forms/TextField";

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
    <div>
      {onSearchChange && (
        <div className="mb-4">
          <TextField
            label={searchLabel}
            value={searchValue ?? ""}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
      )}

      {isLoading ? (
        <div role="status">
          <span className="sr-only">Loading…</span>
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              aria-hidden="true"
              className="mt-2 h-10 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-body text-text-secondary">{emptyMessage}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.header} scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
                    {column.header}
                  </th>
                ))}
                {rowActions && <th scope="col" className="px-3 py-2" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const key = getRowKey(row);
                return (
                  <tr key={key}>
                    {columns.map((column) => (
                      <td key={column.header} className="px-3 py-2 text-body text-text-primary">
                        {column.render(row)}
                      </td>
                    ))}
                    {rowActions && <td className="px-3 py-2">{rowActions(row)}</td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(onPrevious || onNext) && (
        <div className="mt-4 flex items-center justify-between gap-2">
          <Button type="button" onClick={onPrevious} disabled={!hasPrevious}>
            Previous
          </Button>
          <Button type="button" onClick={onNext} disabled={!hasNext}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
