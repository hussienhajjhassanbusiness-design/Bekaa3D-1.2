"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { CustomRequestFunnel } from "@/components/admin/customRequests/CustomRequestFunnel";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import {
  CUSTOM_REQUEST_STATUSES,
  describeCustomRequestStatus,
  isCustomRequestStatus,
  type CustomRequestStatus,
} from "@/lib/admin/customRequests/customRequestPipeline";
import {
  customRequestKeys,
  customRequestsAdminApi,
  type CustomRequestPageDTO,
  type CustomRequestSummaryDTO,
  type CustomRequestsQueryParams,
} from "@/lib/admin/customRequests/customRequestsAdminApi";
import { dayEndExclusive, dayStart } from "@/lib/admin/dateRange";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDate } from "@/lib/orders/orderFormat";

// FVS (phase 6B-2) — /admin/custom-requests, the Bring Your Idea pipeline
// (GET /api/v1/admin/custom-requests) plus the server's funnel. Server
// order: pipeline order, new first then oldest first; closed and lost last.
// Filters are exactly the backend's: status, submitted range, exact email
// (component state only — never written to the page URL).

const COLUMNS: readonly AdminTableColumn<CustomRequestSummaryDTO>[] = [
  {
    header: "Project",
    render: (row) => (
      <Link href={`/admin/custom-requests/${row.id}`} className="break-words text-text-link underline">
        {row.project_title}
      </Link>
    ),
  },
  { header: "From", render: (row) => row.name },
  { header: "Email", render: (row) => <span className="break-all">{row.email}</span> },
  {
    header: "Status",
    render: (row) => {
      const { label, tone } = describeCustomRequestStatus(row.status);
      return <StatusBadge label={label} tone={tone} />;
    },
  },
  {
    header: "Quote",
    render: (row) =>
      row.quoted_amount_cents !== null && row.currency ? <PriceDisplay amountCents={row.quoted_amount_cents} currency={row.currency} /> : "—",
  },
  { header: "Images", render: (row) => row.attachment_count },
  { header: "Submitted", render: (row) => formatOrderDate(row.created_at) },
];

export default function AdminCustomRequestsPage() {
  const [status, setStatus] = useState<CustomRequestStatus | "">("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [email, setEmail] = useState("");
  const pagination = useCursorPagination(JSON.stringify({ status, from, to, email }));

  const query: CustomRequestsQueryParams = {
    ...(status ? { status } : {}),
    ...(dayStart(from) ? { created_after: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { created_before: dayEndExclusive(to) } : {}),
    ...(email ? { email } : {}),
    ...(pagination.cursor ? { cursor: pagination.cursor } : {}),
  };
  const list = useQuery<CustomRequestPageDTO, ApiError>({
    queryKey: customRequestKeys.list(query),
    queryFn: () => customRequestsAdminApi.listRequests(query),
  });

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Bring Your Idea</h1>
      <p className="mt-2 text-body text-text-secondary">
        Custom print requests. Follow up by email or phone, then move each request along. A request is a lead: quotes are
        recorded here, never charged.
      </p>
      <CustomRequestFunnel />
      <h2 className="mt-6 text-h3 font-semibold text-text-primary">Requests</h2>
      <div className="mt-3 grid gap-3 tablet:grid-cols-3">
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setStatus(isCustomRequestStatus(e.target.value) ? e.target.value : "")}
        >
          <option value="">Any status</option>
          {CUSTOM_REQUEST_STATUSES.map((value) => (
            <option key={value} value={value}>
              {describeCustomRequestStatus(value).label}
            </option>
          ))}
        </SelectField>
        <TextField label="Submitted after" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Submitted before" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setEmail(emailDraft.trim());
        }}
      >
        <div className="min-w-[240px] flex-1">
          <TextField
            label="Requester email (exact)"
            type="email"
            autoComplete="off"
            maxLength={254}
            value={emailDraft}
            onChange={(e) => setEmailDraft(e.target.value)}
          />
        </div>
        <Button type="submit">Filter</Button>
        {email && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setEmail("");
              setEmailDraft("");
            }}
          >
            Clear email
          </Button>
        )}
      </form>
      {list.isError && (
        <div className="mt-4">
          <Alert variant="error" message={describeAdminError(list.error)} />
        </div>
      )}
      <div className="mt-4">
        <AdminTable
          columns={COLUMNS}
          rows={list.data?.items ?? []}
          getRowKey={(row) => row.id}
          isLoading={list.isLoading}
          emptyMessage="No requests match these filters."
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
