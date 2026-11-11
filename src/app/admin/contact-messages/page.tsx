"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { CONTACT_MESSAGE_STATUSES, describeContactMessageStatus } from "@/lib/admin/contactMessageWorkflow";
import { normalizeContactStatusFilter, type ContactStatusFilter } from "@/lib/admin/contactQueueFilter";
import {
  contactMessageKeys,
  contactMessagesAdminApi,
  type ContactMessageDTO,
  type ContactMessagePageDTO,
  type ContactMessagesQueryParams,
} from "@/lib/admin/contactMessages/contactMessagesAdminApi";
import { dayEndExclusive, dayStart } from "@/lib/admin/dateRange";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// FVS (phase 6B-1) — /admin/contact-messages, the contact queue
// (GET /api/v1/admin/contact-messages). Server order: new first, then oldest
// first. Filters are exactly the backend's: status, received date range,
// exact sender email. Filters live in component state only — the sender
// email (PII) is never written to the page URL.

const COLUMNS: readonly AdminTableColumn<ContactMessageDTO>[] = [
  {
    header: "From",
    render: (row) => (
      <Link href={`/admin/contact-messages/${row.id}`} className="text-text-link underline">
        {row.name}
      </Link>
    ),
  },
  { header: "Email", render: (row) => <span className="break-all">{row.email}</span> },
  {
    header: "Subject",
    render: (row) => (
      <span>
        {row.subject ?? <span className="text-text-secondary">No subject</span>}
        {row.order_id && (
          <span className="ml-2">
            <StatusBadge label="Order problem" tone="negative" />
          </span>
        )}
      </span>
    ),
  },
  {
    header: "Status",
    render: (row) => {
      const { label, tone } = describeContactMessageStatus(row.status);
      return <StatusBadge label={label} tone={tone} />;
    },
  },
  { header: "Received", render: (row) => formatOrderDateTime(row.created_at) },
];

export default function AdminContactMessagesPage() {
  const [status, setStatus] = useState<ContactStatusFilter>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [emailDraft, setEmailDraft] = useState("");
  const [email, setEmail] = useState("");
  const pagination = useCursorPagination(JSON.stringify({ status, from, to, email }));

  const query: ContactMessagesQueryParams = {
    ...(status !== "all" ? { status } : {}),
    ...(dayStart(from) ? { created_after: dayStart(from) } : {}),
    ...(dayEndExclusive(to) ? { created_before: dayEndExclusive(to) } : {}),
    ...(email ? { email } : {}),
    ...(pagination.cursor ? { cursor: pagination.cursor } : {}),
  };
  const list = useQuery<ContactMessagePageDTO, ApiError>({
    queryKey: contactMessageKeys.list(query),
    queryFn: () => contactMessagesAdminApi.listMessages(query),
  });

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Contact messages</h1>
      <p className="mt-2 text-body text-text-secondary">
        Messages from the contact form and customers&apos; order problem reports. Reply by email, then move the message
        along. Opening a message doesn&apos;t mark it read.
      </p>
      <div className="mt-4 grid gap-3 tablet:grid-cols-3">
        <SelectField label="Status" value={status} onChange={(e) => setStatus(normalizeContactStatusFilter(e.target.value))}>
          <option value="all">Any status</option>
          {CONTACT_MESSAGE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {describeContactMessageStatus(value).label}
            </option>
          ))}
        </SelectField>
        <TextField label="Received from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Received to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
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
            label="Sender email (exact)"
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
          emptyMessage="No messages match these filters."
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
