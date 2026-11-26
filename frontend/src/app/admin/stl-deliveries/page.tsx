"use client";

import { useState } from "react";
import Link from "next/link";
import { AdminActionDialog } from "@/components/admin/orders/AdminActionDialog";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { adminOrdersApi } from "@/lib/admin/orders/adminOrdersApi";
import type { StlDeliveryReadDTO } from "@/lib/admin/orders/adminOrderTypes";
import { useAdminOrderWrite, useStlDeliveries } from "@/lib/admin/orders/useAdminOrders";
import { useCursorPagination } from "@/lib/admin/useCursorPagination";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";

// FVS-030 (phase 5H) — the STL delivery queue, GET /api/v1/admin/stl-deliveries:
// every paid STL line still owed, oldest first. ADR-019: the file is
// emailed BY HAND outside this site; this page only records that it was
// sent (the line's `awaiting_delivery -> delivered` transition). No upload,
// download, link or entitlement exists or is shown.
export default function AdminStlDeliveriesPage() {
  const pagination = useCursorPagination();
  const { data, isLoading, isError, error } = useStlDeliveries({ cursor: pagination.cursor });
  const write = useAdminOrderWrite();
  const [row, setRow] = useState<StlDeliveryReadDTO | null>(null);

  async function confirm() {
    if (!row) return;
    const target = row;
    if (
      await write.run(() =>
        adminOrdersApi.transitionLine(target.order_id, target.item_id, { target_status: "delivered" })
      )
    ) {
      setRow(null);
    }
  }

  const columns: readonly AdminTableColumn<StlDeliveryReadDTO>[] = [
    { header: "File", render: (r) => r.product_name },
    {
      header: "Order",
      render: (r) => (
        <Link
          href={`/admin/orders/${r.order_id}`}
          className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
        >
          {r.order_number}
        </Link>
      ),
    },
    { header: "Customer", render: (r) => r.customer_email },
    { header: "Paid", render: (r) => <PriceDisplay amountCents={r.line_total_cents} currency={r.currency} /> },
    { header: "Waiting since", render: (r) => formatOrderDateTime(r.queued_at) },
  ];

  return (
    <>
      <h1 className="break-words font-headline text-headline-lg text-on-surface">STL deliveries</h1>
      <p className="mt-2 max-w-3xl font-body text-body-md text-on-surface-variant">
        Email each file to the customer yourself, then mark it emailed here.
      </p>
      {isError && (
        <div className="mt-4">
          <Alert variant="error" message={describeAdminError(error)} />
        </div>
      )}
      <div className="mt-6">
        <AdminTable
          columns={columns}
          rows={data?.items ?? []}
          getRowKey={(r) => r.item_id}
          isLoading={isLoading}
          emptyMessage="No STL files are waiting to be emailed."
          hasPrevious={pagination.hasPrevious}
          hasNext={data?.next_cursor != null}
          onPrevious={pagination.goPrevious}
          onNext={() => {
            if (data?.next_cursor) pagination.goNext(data.next_cursor);
          }}
          rowActions={(r) => (
            <Button
              type="button"
              onClick={() => {
                write.reset();
                setRow(r);
              }}
            >
              Mark emailed
            </Button>
          )}
        />
      </div>
      <AdminActionDialog
        open={row !== null}
        title="Mark this STL file emailed?"
        description={
          <p>
            Confirm you have emailed “{row?.product_name}” to {row?.customer_email} (order {row?.order_number}). The
            customer will see it as emailed.
          </p>
        }
        confirmLabel="Mark emailed"
        pending={write.state.kind === "pending"}
        error={write.state.kind === "error" ? write.state.message : null}
        onConfirm={() => void confirm()}
        onClose={() => setRow(null)}
      />
    </>
  );
}
