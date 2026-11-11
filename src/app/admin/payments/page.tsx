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
import { describePaymentProvider } from "@/lib/admin/orders/adminOrderPresentation";
import type { AdminPaymentReadDTO, AdminPaymentsQueryParams } from "@/lib/admin/payments/adminPaymentTypes";
import { useAdminPayments } from "@/lib/admin/payments/useAdminPayments";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { describePaymentStatus } from "@/lib/orders/orderStatus";

// FVS-028 (phase 5I) — GET /api/v1/admin/payments, oldest first. Filters are
// exactly the backend's: status, provider (mock or cash; no live provider
// exists yet, VS-032) and late_captured (the late captures to refund).

const STATUSES = ["pending", "processing", "paid", "partially_refunded", "refunded", "failed", "expired"] as const;

const COLUMNS: readonly AdminTableColumn<AdminPaymentReadDTO>[] = [
  {
    header: "Payment",
    render: (row) => (
      <Link href={`/admin/payments/${row.id}`} className="font-semibold text-text-link underline">
        {row.order_number ? `Order ${row.order_number}` : "View payment"}
      </Link>
    ),
  },
  { header: "Provider", render: (row) => describePaymentProvider(row.provider) },
  {
    header: "Status",
    render: (row) => {
      const d = describePaymentStatus(row.status);
      return (
        <span className="flex flex-wrap items-center gap-1">
          <StatusBadge label={d.label} tone={d.tone} />
          {row.late_captured_at && <StatusBadge label="Late capture" tone="warning" />}
          {row.needs_manual_confirmation && <StatusBadge label="Needs confirmation" tone="warning" />}
        </span>
      );
    },
  },
  { header: "Amount", render: (row) => <PriceDisplay amountCents={row.amount_cents} currency={row.currency} /> },
  { header: "Started", render: (row) => formatOrderDateTime(row.initiated_at) },
];

type Filters = Pick<AdminPaymentsQueryParams, "status" | "provider" | "late_captured">;

function AdminPaymentsPageContent() {
  const params = useSearchParams();
  const orderParam = params.get("order_id");
  const orderId = orderParam && isOrderId(orderParam) ? orderParam : undefined;
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState<Filters>({});
  const pagination = useCursorPagination(JSON.stringify({ ...filters, orderId, from, to }));
  const { data, isLoading, isError, error } = useAdminPayments({
    ...filters,
    ...(orderId ? { order_id: orderId } : {}),
    ...(dayStart(from) ? { initiated_after: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { initiated_before: dayEndExclusive(to) } : {}),
    cursor: pagination.cursor,
  });

  function set<K extends keyof Filters>(key: K, value: Filters[K] | undefined) {
    setFilters((current) => {
      const next = { ...current };
      if (value === undefined) delete next[key];
      else next[key] = value;
      return next;
    });
  }

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Payments</h1>
      {orderId && (
        <p className="mt-2 text-body text-text-primary">
          Showing one order&apos;s payments.{" "}
          <Link href="/admin/payments" className="text-text-link underline">
            Show all
          </Link>
        </p>
      )}
      <div className="mt-4 grid gap-3 tablet:grid-cols-2 desktop:grid-cols-5">
        <TextField label="Started from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Started to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <SelectField label="Status" value={filters.status ?? ""} onChange={(e) => set("status", (e.target.value || undefined) as Filters["status"])}>
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {describePaymentStatus(s).label}
            </option>
          ))}
        </SelectField>
        <SelectField label="Provider" value={filters.provider ?? ""} onChange={(e) => set("provider", (e.target.value || undefined) as Filters["provider"])}>
          <option value="">Any</option>
          <option value="mock">Online (mock provider)</option>
          <option value="cash">Cash</option>
        </SelectField>
        <SelectField
          label="Late captures"
          value={filters.late_captured === undefined ? "" : String(filters.late_captured)}
          onChange={(e) => set("late_captured", e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="">All payments</option>
          <option value="true">Late captures to refund</option>
        </SelectField>
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
          emptyMessage="No payments match these filters."
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
export default function AdminPaymentsPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <AdminPaymentsPageContent />
    </Suspense>
  );
}
