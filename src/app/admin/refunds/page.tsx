"use client";

import { useState } from "react";
import Link from "next/link";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { SelectField } from "@/components/forms/SelectField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { describeAdminRefundKind, describeAdminRefundStatus } from "@/lib/admin/orders/adminOrderPresentation";
import type { AdminRefundsQueryParams, RefundDetailDTO } from "@/lib/admin/payments/adminPaymentTypes";
import { useAdminRefunds } from "@/lib/admin/payments/useAdminPayments";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// FVS-028 (phase 5I) — GET /api/v1/admin/refunds. Default: the obligations
// queue (pending or still owed, oldest first); "History" is queue=false.
// Filters are the backend's own (kind, status for the history).

const COLUMNS: readonly AdminTableColumn<RefundDetailDTO>[] = [
  {
    header: "Refund",
    render: (row) => (
      <Link href={`/admin/refunds/${row.id}`} className="font-semibold text-text-link underline">
        Order {row.order_number}
      </Link>
    ),
  },
  { header: "Kind", render: (row) => describeAdminRefundKind(row.kind) },
  {
    header: "Status",
    render: (row) => {
      const d = describeAdminRefundStatus(row.status);
      return (
        <span className="flex flex-wrap gap-1">
          <StatusBadge label={d.label} tone={d.tone} />
          {row.owed && <StatusBadge label="Still owed" tone="warning" />}
        </span>
      );
    },
  },
  { header: "Amount", render: (row) => <PriceDisplay amountCents={row.amount_cents} currency={row.currency} /> },
  { header: "Recorded", render: (row) => formatOrderDateTime(row.created_at) },
];

type Filters = Pick<AdminRefundsQueryParams, "queue" | "kind" | "status">;

export default function AdminRefundsPage() {
  const [filters, setFilters] = useState<Filters>({ queue: true });
  const pagination = useCursorPagination(JSON.stringify(filters));
  const { data, isLoading, isError, error } = useAdminRefunds({ ...filters, cursor: pagination.cursor });

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Refunds</h1>
      <div className="mt-4 grid gap-3 tablet:grid-cols-3">
        <SelectField
          label="View"
          value={filters.queue ? "queue" : "history"}
          onChange={(e) => setFilters((f) => ({ kind: f.kind, queue: e.target.value === "queue" }))}
        >
          <option value="queue">To pay (pending or owed)</option>
          <option value="history">History</option>
        </SelectField>
        <SelectField
          label="Kind"
          value={filters.kind ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, kind: (e.target.value || undefined) as Filters["kind"] }))}
        >
          <option value="">Any</option>
          <option value="admin">Admin refund</option>
          <option value="cancellation">Cancellation refund</option>
          <option value="late_capture">Late capture refund</option>
        </SelectField>
        {!filters.queue && (
          <SelectField
            label="Status"
            value={filters.status ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, status: (e.target.value || undefined) as Filters["status"] }))}
          >
            <option value="">Any</option>
            <option value="pending">Pending</option>
            <option value="settled">Settled</option>
            <option value="failed">Failed</option>
            <option value="voided">Voided</option>
          </SelectField>
        )}
      </div>
      {isError && (
        <div className="mt-4">
          <Alert variant="error" message={describeAdminError(error)} />
        </div>
      )}
      <div className="mt-4">
        <AdminTable
          columns={COLUMNS}
          rows={data?.items ?? []}
          getRowKey={(row) => row.id}
          isLoading={isLoading}
          emptyMessage={filters.queue ? "No refunds are waiting to be paid." : "No refunds match these filters."}
          hasPrevious={pagination.hasPrevious}
          hasNext={data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (data?.next_cursor) pagination.goNext(data.next_cursor);
          }}
        />
      </div>
    </>
  );
}
