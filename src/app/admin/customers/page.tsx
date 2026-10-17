"use client";

import { useState } from "react";
import Link from "next/link";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge, describeAdminAccountStatus } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { useAdminUsers } from "@/lib/admin/customers/useAdminUsers";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { useDebouncedValue } from "@/lib/shared/useDebouncedValue";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import type { AdminUserDetail } from "@/lib/admin/customers/customerTypes";

const SEARCH_DEBOUNCE_MS = 300;

const COLUMNS: readonly AdminTableColumn<AdminUserDetail>[] = [
  { header: "Email", render: (row) => row.email },
  {
    header: "Status",
    render: (row) => {
      const { label, tone } = describeAdminAccountStatus(row.is_active ? "active" : "deactivated");
      return <StatusBadge label={label} tone={tone} />;
    },
  },
  { header: "Verified", render: (row) => (row.email_verified_at ? "Yes" : "No") },
  { header: "Joined", render: (row) => new Date(row.created_at).toLocaleDateString() },
];

export default function AdminCustomersPage() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);
  const pagination = useCursorPagination(debouncedSearch);

  const { data, isLoading, isError, error } = useAdminUsers({
    cursor: pagination.cursor,
    search: debouncedSearch || undefined,
  });

  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Customers</h1>
      {isError && <Alert variant="error" message={describeAdminError(error)} />}
      <div className="mt-4">
        <AdminTable
          columns={COLUMNS}
          rows={data?.items ?? []}
          getRowKey={(row) => row.id}
          isLoading={isLoading}
          emptyMessage="No customers found."
          searchValue={search}
          onSearchChange={setSearch}
          searchLabel="Search by email"
          hasPrevious={pagination.hasPrevious}
          hasNext={data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (data?.next_cursor) {
              pagination.goNext(data.next_cursor);
            }
          }}
          rowActions={(row) => (
            <Link href={`/admin/customers/${row.id}`} className="text-text-link underline">
              View
            </Link>
          )}
        />
      </div>
    </>
  );
}
