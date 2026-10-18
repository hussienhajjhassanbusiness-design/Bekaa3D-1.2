"use client";

import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import type { OrderListFilters, OrderListItemModel } from "@/lib/orders/orderModel";

export interface OrderListStatusOption {
  value: string;
  label: string;
}

export interface OrderListProps {
  items: readonly OrderListItemModel[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  // Caller/config-driven — never a hardcoded status list. Omitted
  // entirely means no status filter renders at all.
  statusOptions?: readonly OrderListStatusOption[];
  filters: OrderListFilters;
  onFiltersChange: (next: OrderListFilters) => void;
  // Forward-only cursor seam — no Previous control anywhere, since
  // VS-023 only confirms "cursor pagination," not bidirectional
  // support (FVS-029-IMPLEMENTATION-PLAN.md §0/T05).
  hasNext?: boolean;
  onNext?: () => void;
}

const EMPTY_MESSAGE = "You have no orders yet.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your orders. Please try again.";

// #FVS029-ORDER-LIST
//
// Presentational only — no network, no query. Desktop/tablet renders
// a real <table>; mobile renders a stacked list — both exist in the
// DOM simultaneously with CSS-only visibility switching, so there is
// no duplicate screen-reader announcement and no JS viewport
// detection. No fake rows are ever rendered.
export function OrderList({
  items,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  statusOptions,
  filters,
  onFiltersChange,
  hasNext = false,
  onNext,
}: OrderListProps) {
  const statusId = useId();
  const fromId = useId();
  const toId = useId();

  const filterBar = (
    <div className="mb-4 flex flex-wrap items-end gap-3">
      {statusOptions && (
        <div>
          <label htmlFor={statusId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
            Status
          </label>
          <select
            id={statusId}
            value={filters.status ?? ""}
            onChange={(event) => onFiltersChange({ ...filters, status: event.target.value || null })}
            className="mt-1 rounded-sm border border-border-default px-2 py-1 text-body"
          >
            <option value="">All</option>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}
      <div>
        <label htmlFor={fromId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          From
        </label>
        <input
          id={fromId}
          type="date"
          value={filters.dateFrom ?? ""}
          onChange={(event) => onFiltersChange({ ...filters, dateFrom: event.target.value || null })}
          className="mt-1 rounded-sm border border-border-default px-2 py-1 text-body"
        />
      </div>
      <div>
        <label htmlFor={toId} className="block text-label font-semibold uppercase tracking-label text-text-primary">
          To
        </label>
        <input
          id={toId}
          type="date"
          value={filters.dateTo ?? ""}
          onChange={(event) => onFiltersChange({ ...filters, dateTo: event.target.value || null })}
          className="mt-1 rounded-sm border border-border-default px-2 py-1 text-body"
        />
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div>
        {filterBar}
        <div role="status">
          <span className="sr-only">Loading your orders…</span>
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              aria-hidden="true"
              className="mt-2 h-14 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        {filterBar}
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
    return (
      <div>
        {filterBar}
        <EmptyState message={EMPTY_MESSAGE} />
      </div>
    );
  }

  return (
    <div>
      {filterBar}

      <table className="hidden w-full text-left tablet:table">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
              Date
            </th>
            <th scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
              Status
            </th>
            <th scope="col" className="px-3 py-2 text-label font-semibold uppercase tracking-label text-text-secondary">
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="px-3 py-2 text-body text-text-primary">{item.displayDate}</td>
              <td className="px-3 py-2">
                <StatusBadge label={item.statusLabel} tone="neutral" />
              </td>
              <td className="px-3 py-2 text-body text-text-primary">
                {item.totalCents !== undefined && item.currency && (
                  <PriceDisplay amountCents={item.totalCents} currency={item.currency} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="tablet:hidden">
        {items.map((item) => (
          <li key={item.id} className="border-b border-border-default py-3">
            <p className="text-body text-text-primary">{item.displayDate}</p>
            <div className="mt-1 flex items-center justify-between gap-2">
              <StatusBadge label={item.statusLabel} tone="neutral" />
              {item.totalCents !== undefined && item.currency && (
                <PriceDisplay amountCents={item.totalCents} currency={item.currency} />
              )}
            </div>
          </li>
        ))}
      </ul>

      {hasNext && onNext && (
        <Button type="button" onClick={onNext} className="mt-4">
          Load more
        </Button>
      )}
    </div>
  );
}
