"use client";

import { useState } from "react";
import Link from "next/link";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { SelectField } from "@/components/forms/SelectField";
import { useAdminProducts } from "@/lib/admin/products/useAdminProducts";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { useDebouncedValue } from "@/lib/shared/useDebouncedValue";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import type { ProductType, RawAdminProductDetail } from "@/lib/admin/products/productAdminTypes";

const SEARCH_DEBOUNCE_MS = 300;

const COLUMNS: readonly AdminTableColumn<RawAdminProductDetail>[] = [
  { header: "Name", render: (row) => row.name },
  { header: "Type", render: (row) => (row.type === "physical" ? "Physical" : "STL") },
  { header: "Price", render: (row) => <PriceDisplay amountCents={row.price.amount_cents} currency={row.price.currency} /> },
  {
    header: "Visibility",
    render: (row) => <StatusBadge label={row.is_visible ? "Visible" : "Hidden"} tone={row.is_visible ? "positive" : "neutral"} />,
  },
  {
    header: "Availability",
    render: (row) => (
      <StatusBadge label={row.is_available ? "Available" : "Unavailable"} tone={row.is_available ? "positive" : "warning"} />
    ),
  },
];

export default function AdminProductsPage() {
  const [search, setSearch] = useState("");
  const [type, setType] = useState<ProductType | "">("");
  const debouncedSearch = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);
  const pagination = useCursorPagination(`${debouncedSearch}|${type}`);

  const { data, isLoading, isError, error } = useAdminProducts({
    cursor: pagination.cursor,
    q: debouncedSearch || undefined,
    type: type || undefined,
  });

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-h1 font-bold text-text-primary">Products</h1>
        <Link href="/admin/products/new">
          <Button type="button">New product</Button>
        </Link>
      </div>

      {isError && <Alert variant="error" message={describeAdminError(error)} />}

      <div className="mt-4 max-w-xs">
        <SelectField label="Type" value={type} onChange={(e) => setType(e.target.value as ProductType | "")}>
          <option value="">All types</option>
          <option value="physical">Physical</option>
          <option value="stl">STL</option>
        </SelectField>
      </div>

      <div className="mt-4">
        <AdminTable
          columns={COLUMNS}
          rows={data?.items ?? []}
          getRowKey={(row) => row.id}
          isLoading={isLoading}
          emptyMessage="No products found."
          searchValue={search}
          onSearchChange={setSearch}
          searchLabel="Search by name"
          hasPrevious={pagination.hasPrevious}
          hasNext={data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (data?.next_cursor) {
              pagination.goNext(data.next_cursor);
            }
          }}
          rowActions={(row) => (
            <Link href={`/admin/products/${row.id}`} className="text-text-link underline">
              View
            </Link>
          )}
        />
      </div>
    </>
  );
}
