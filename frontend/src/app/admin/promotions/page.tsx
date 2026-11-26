"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Alert } from "@/components/feedback/Alert";
import { buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { describeAdminError } from "@/lib/admin/adminErrorMessages";
import { adminPromotionKeys, promotionsAdminApi } from "@/lib/admin/promotions/promotionsAdminApi";
import type { ApiError } from "@/lib/api/ApiError";
import { formatOrderDateTime } from "@/lib/orders/orderFormat";
import { describePromotionStatus, discountAmount, promotionScopeLabel } from "@/lib/promotions/promotionFormat";
import { PROMOTION_CURRENCY, type AdminPromotionList, type AdminPromotionRead } from "@/lib/promotions/promotionTypes";

// /admin/promotions — seasonal store/product price campaigns (Eid, Ramadan,
// Christmas…), GET /api/v1/admin/promotions. Status is the server's own,
// derived from `active` and the window. Not Offers (customer negotiation).
const COLUMNS: readonly AdminTableColumn<AdminPromotionRead>[] = [
  {
    header: "Name",
    render: (row) => (
      <Link
        href={`/admin/promotions/${encodeURIComponent(row.id)}`}
        className="font-semibold text-primary underline underline-offset-2 hover:text-primary-container"
      >
        {row.name}
      </Link>
    ),
  },
  {
    header: "Discount",
    render: (row) => (
      <span className="font-label font-bold text-on-secondary-container">
        {discountAmount(row.discount_type, row.discount_value, PROMOTION_CURRENCY)} off
      </span>
    ),
  },
  {
    header: "Scope",
    render: (row) =>
      row.scope === "selected"
        ? `${promotionScopeLabel(row.scope)} (${row.product_ids.length})`
        : promotionScopeLabel(row.scope),
  },
  { header: "Start", render: (row) => formatOrderDateTime(row.starts_at) },
  { header: "End", render: (row) => formatOrderDateTime(row.ends_at) },
  {
    header: "Status",
    render: (row) => {
      const status = describePromotionStatus(row.status);
      return <StatusBadge label={status.label} tone={status.tone} />;
    },
  },
];

export default function AdminPromotionsPage() {
  const list = useQuery<AdminPromotionList, ApiError>({
    queryKey: adminPromotionKeys.list(),
    queryFn: promotionsAdminApi.listPromotions,
  });

  return (
    <>
      <PageHeader
        title="Promotions"
        description="Store-wide price campaigns such as Eid, Ramadan or Christmas sales. While a promotion is active, the shop, cart and checkout charge its discounted prices. An active promotion also appears on the homepage."
        actions={
          <Link href="/admin/promotions/new" className={buttonLinkClassName("primary")}>
            <Icon name="add" className="h-4 w-4" />
            Create promotion
          </Link>
        }
      />
      {list.isError && (
        <div className="mb-4">
          <Alert variant="error" message={describeAdminError(list.error)} />
        </div>
      )}
      <AdminTable
        columns={COLUMNS}
        rows={list.data?.items ?? []}
        getRowKey={(row) => row.id}
        isLoading={list.isLoading}
        emptyMessage="No promotions yet. Create one for your next seasonal sale."
      />
    </>
  );
}
