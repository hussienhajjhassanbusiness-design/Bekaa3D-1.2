import { AdminTable, type AdminTableColumn } from "@/components/admin/AdminTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { Button } from "@/components/forms/Button";
import { describeAdminPaymentStatus, type AdminPaymentModel } from "@/lib/admin/adminPaymentModel";

export interface AdminPaymentListProps {
  payments: readonly AdminPaymentModel[];
  isLoading?: boolean;
  onSelectPayment?: (paymentId: string) => void;
}

const COLUMNS: readonly AdminTableColumn<AdminPaymentModel>[] = [
  {
    header: "Status",
    render: (payment) => {
      const { label, tone } = describeAdminPaymentStatus(payment.status);
      return <StatusBadge label={label} tone={tone} />;
    },
  },
  {
    header: "Amount",
    render: (payment) => <PriceDisplay amountCents={payment.amountCents} currency={payment.currency} />,
  },
  { header: "Provider", render: (payment) => payment.providerDisplayLabel },
  { header: "Provider Reference", render: (payment) => payment.providerReferenceDisplayValue },
  { header: "Linked Order", render: (payment) => payment.linkedOrderDisplayId },
];

// #SHARED-ADMIN-TABLE reuse — no second table implementation. Every
// value is plain/non-clickable: no admin order/payment-detail route
// exists yet to link to. `onSelectPayment` is a presentational seam
// only — never a real navigation.
export function AdminPaymentList({ payments, isLoading, onSelectPayment }: AdminPaymentListProps) {
  return (
    <AdminTable
      columns={COLUMNS}
      rows={payments}
      getRowKey={(payment) => payment.id}
      isLoading={isLoading}
      rowActions={
        onSelectPayment
          ? (payment) => (
              <Button type="button" onClick={() => onSelectPayment(payment.id)}>
                View
              </Button>
            )
          : undefined
      }
    />
  );
}
