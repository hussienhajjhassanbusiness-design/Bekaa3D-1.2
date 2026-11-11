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
import type { AdminOrderSummaryReadDTO, AdminOrdersQueryParams } from "@/lib/admin/orders/adminOrderTypes";
import { useAdminOrders } from "@/lib/admin/orders/useAdminOrders";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { formatOrderDate, fulfillmentLabel, paymentMethodLabel } from "@/lib/orders/orderFormat";
import { describeOrderStatus } from "@/lib/orders/orderStatus";
import { useDebouncedValue } from "@/lib/shared/useDebouncedValue";

// FVS-030 (phase 5H) — the fulfillment queue, GET /api/v1/admin/orders.
// Protection: AdminShell's AdminGuard (admin + MFA); a customer gets 404.
// Filters are exactly the backend's: status (never pending_payment: unpaid
// online orders are not in the queue), fulfillment method, payment method,
// the "cash due" view (payment_due), an order-number lookup, and (phase 6A)
// ?customer_id from the customer page plus a placed-date range. Newest
// first, keyset cursor, no total count, no invented metrics.

const STATUS_OPTIONS = [
  ["in_progress", "In progress"],
  ["completed", "Completed"],
  ["partially_refunded", "Partially refunded"],
  ["refunded", "Refunded"],
  ["cancelled", "Cancelled"],
] as const;

const COLUMNS: readonly AdminTableColumn<AdminOrderSummaryReadDTO>[] = [
  {
    header: "Order",
    render: (row) => (
      <Link href={`/admin/orders/${row.id}`} className="font-semibold text-text-link underline">
        {row.order_number}
      </Link>
    ),
  },
  { header: "Customer", render: (row) => row.customer_email },
  {
    header: "Status",
    render: (row) => {
      const d = describeOrderStatus(row.status);
      return <StatusBadge label={d.label} tone={d.tone} />;
    },
  },
  { header: "Fulfillment", render: (row) => fulfillmentLabel(row.fulfillment_method) },
  {
    header: "Payment",
    render: (row) =>
      row.payment_due && row.amount_due ? (
        <span>
          Cash due <PriceDisplay amountCents={row.amount_due.amount_cents} currency={row.amount_due.currency} />
        </span>
      ) : (
        paymentMethodLabel(row.payment_method)
      ),
  },
  { header: "Total", render: (row) => <PriceDisplay amountCents={row.total.amount_cents} currency={row.total.currency} /> },
  { header: "Placed", render: (row) => formatOrderDate(row.placed_at) },
];

type Filters = Pick<AdminOrdersQueryParams, "status" | "fulfillment_method" | "payment_method" | "payment_due">;

function AdminOrdersPageContent() {
  const params = useSearchParams();
  const customerParam = params.get("customer_id");
  const customerId = customerParam && isOrderId(customerParam) ? customerParam : undefined;
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState<Filters>({});
  const [orderNumber, setOrderNumber] = useState("");
  const number = useDebouncedValue(orderNumber.trim(), 300);
  const pagination = useCursorPagination(JSON.stringify({ ...filters, number, customerId, from, to }));
  const { data, isLoading, isError, error } = useAdminOrders({
    ...filters,
    ...(customerId ? { customer_id: customerId } : {}),
    ...(dayStart(from) ? { placed_after: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { placed_before: dayEndExclusive(to) } : {}),
    order_number: number || undefined,
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
      <h1 className="text-h1 font-bold text-text-primary">Orders</h1>
      {customerId && (
        <p className="mt-2 text-body text-text-primary">
          Showing one customer&apos;s orders.{" "}
          <Link href="/admin/orders" className="text-text-link underline">
            Show all
          </Link>
        </p>
      )}
      <div className="mt-4 grid gap-3 tablet:grid-cols-2 desktop:grid-cols-6">
        <TextField label="Placed from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Placed to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <SelectField
          label="Status"
          value={filters.status ?? ""}
          onChange={(e) => set("status", (e.target.value || undefined) as Filters["status"])}
        >
          <option value="">Any status</option>
          {STATUS_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Fulfillment"
          value={filters.fulfillment_method ?? ""}
          onChange={(e) => set("fulfillment_method", (e.target.value || undefined) as Filters["fulfillment_method"])}
        >
          <option value="">Any</option>
          <option value="delivery">Delivery</option>
          <option value="pickup">Pickup</option>
        </SelectField>
        <SelectField
          label="Payment"
          value={filters.payment_method ?? ""}
          onChange={(e) => set("payment_method", (e.target.value || undefined) as Filters["payment_method"])}
        >
          <option value="">Any</option>
          <option value="cash">Cash</option>
          <option value="online">Online</option>
        </SelectField>
        <SelectField
          label="Cash due"
          value={filters.payment_due === undefined ? "" : String(filters.payment_due)}
          onChange={(e) => set("payment_due", e.target.value === "" ? undefined : e.target.value === "true")}
        >
          <option value="">All orders</option>
          <option value="true">Cash due only</option>
          <option value="false">No cash due</option>
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
          emptyMessage="No orders match these filters."
          searchValue={orderNumber}
          onSearchChange={setOrderNumber}
          searchLabel="Order number"
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
export default function AdminOrdersPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <AdminOrdersPageContent />
    </Suspense>
  );
}
