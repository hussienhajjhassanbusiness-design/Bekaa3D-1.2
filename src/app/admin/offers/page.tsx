"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { SelectField } from "@/components/forms/SelectField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { adminOfferKeys, offersAdminApi, type AdminOffersQueryParams } from "@/lib/admin/offers/offersAdminApi";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import type { ApiError } from "@/lib/api/ApiError";
import {
  OFFER_STATUSES,
  describeOfferStatus,
  formatMoney,
  isOfferStatus,
  offerDeadline,
  offerProductName,
} from "@/lib/offers/offerModel";
import type { AdminOfferPageDTO, AdminOfferSummaryReadDTO, OfferStatus } from "@/lib/offers/offerTypes";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// FVS (phase 6C) — /admin/offers, the offer queue (GET /api/v1/admin/offers).
// Server order: the administrator's turn first, then the soonest deadline.
// The only filter offered is the backend's status filter; it lives in
// component state (no customer data ever goes into the page URL).

const COLUMNS: readonly AdminTableColumn<AdminOfferSummaryReadDTO>[] = [
  {
    header: "Product",
    render: (row) => (
      <Link
        href={`/admin/offers/${encodeURIComponent(row.id)}`}
        className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
      >
        {offerProductName(row.product.name)}
      </Link>
    ),
  },
  {
    header: "Customer",
    render: (row) => <span className="break-all">{row.customer.email ?? "Unknown customer"}</span>,
  },
  {
    header: "Status",
    render: (row) => {
      const { label, tone } = describeOfferStatus(row.status, "admin");
      return <StatusBadge label={label} tone={tone} />;
    },
  },
  { header: "Amount", render: (row) => formatMoney(row.agreed_amount ?? row.current_amount) },
  {
    header: "Deadline",
    render: (row) => {
      const deadline = offerDeadline(row);
      if (!deadline) return <span className="text-on-surface-variant">—</span>;
      return `${deadline.kind === "checkout" ? "Checkout by" : "Reply by"} ${formatOrderDateTime(deadline.at)}`;
    },
  },
  { header: "Opened", render: (row) => formatOrderDateTime(row.created_at) },
];

type StatusFilter = OfferStatus | "all";

export default function AdminOffersPage() {
  const [status, setStatus] = useState<StatusFilter>("all");
  const pagination = useCursorPagination(status);
  const query: AdminOffersQueryParams = {
    ...(status !== "all" ? { status } : {}),
    ...(pagination.cursor ? { cursor: pagination.cursor } : {}),
  };
  const list = useQuery<AdminOfferPageDTO, ApiError>({
    queryKey: adminOfferKeys.list(query),
    queryFn: () => offersAdminApi.listOffers(query),
  });

  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">Offers</h1>
      <p className="mt-2 max-w-3xl font-body text-body-md text-on-surface-variant">
        Customers&apos; price offers on STL products. Offers waiting for your reply come first, soonest deadline first.
        An offer expires if its reply deadline passes.
      </p>
      <div className="mt-4 max-w-xs">
        <SelectField
          label="Status"
          value={status}
          onChange={(event) => setStatus(isOfferStatus(event.target.value) ? event.target.value : "all")}
        >
          <option value="all">Any status</option>
          {OFFER_STATUSES.map((value) => (
            <option key={value} value={value}>
              {describeOfferStatus(value, "admin").label}
            </option>
          ))}
        </SelectField>
      </div>
      {list.isError && (
        <div className="mt-4">
          <Alert variant="error" message={describeAdminError(list.error)} />
        </div>
      )}
      <div className="mt-6">
        <AdminTable
          columns={COLUMNS}
          rows={list.data?.items ?? []}
          getRowKey={(row) => row.id}
          isLoading={list.isLoading}
          emptyMessage="No offers match this filter."
          hasPrevious={pagination.hasPrevious}
          hasNext={list.data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (list.data?.next_cursor) pagination.goNext(list.data.next_cursor);
          }}
        />
      </div>
    </>
  );
}
