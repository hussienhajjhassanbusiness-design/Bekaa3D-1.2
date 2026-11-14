"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { TextField } from "@/components/forms/TextField";
import { dayEndExclusive, dayStart } from "@/lib/admin/dateRange";
import { isOrderId } from "@/lib/orders/orderModel";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
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
      <Link
        href={`/admin/refunds/${row.id}`}
        className="whitespace-nowrap font-label font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
      >
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

function AdminRefundsPageContent() {
  const params = useSearchParams();
  const uuid = (key: string) => {
    const value = params.get(key);
    return value && isOrderId(value) ? value : undefined;
  };
  const customerId = uuid("customer_id");
  const orderId = uuid("order_id");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState<Filters>({ queue: true });
  const pagination = useCursorPagination(JSON.stringify({ ...filters, customerId, orderId, from, to }));
  const { data, isLoading, isError, error } = useAdminRefunds({
    ...filters,
    ...(customerId ? { customer_id: customerId } : {}),
    ...(orderId ? { order_id: orderId } : {}),
    ...(dayStart(from) ? { created_from: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { created_to: dayEndExclusive(to) } : {}),
    cursor: pagination.cursor,
  });

  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Refunds</h1>
      {(customerId || orderId) && (
        <p className="mt-4 rounded-control border border-info-outline bg-info-container px-4 py-3 font-body text-body-md text-on-info-container">
          Showing one {customerId ? "customer" : "order"}&apos;s refunds.{" "}
          <Link
            href="/admin/refunds"
            className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
          >
            Show all
          </Link>
        </p>
      )}
      <div className="mt-6 grid gap-4 rounded-card border border-outline-variant/40 bg-surface-container-lowest p-4 shadow-sm tablet:p-6 tablet:grid-cols-2 desktop:grid-cols-5">
        <TextField label="Recorded from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Recorded to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
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
      <div className="mt-6">
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

// useSearchParams() needs a Suspense boundary to keep the page prerenderable
// (Next.js App Router; same convention as /login).
export default function AdminRefundsPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <AdminRefundsPageContent />
    </Suspense>
  );
}
