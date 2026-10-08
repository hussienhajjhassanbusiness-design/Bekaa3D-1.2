import { Button } from "@/components/forms/Button";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { describeAdminPaymentStatus, type AdminPaymentModel } from "@/lib/admin/adminPaymentModel";

export interface PaymentDetailProps {
  payment: AdminPaymentModel;
  onReconcile: (paymentId: string) => void;
  isReconciling?: boolean;
}

// #SECURITY-PAYMENT-OPERATIONS-DATA
//
// Presentational only — no network. Renders only confirmed
// conceptual fields; never a raw provider payload/JSON blob viewer.
// Reconciliation never optimistically changes the displayed status —
// only a future server response/refetch is authoritative.
export function PaymentDetail({ payment, onReconcile, isReconciling = false }: PaymentDetailProps) {
  const { label, tone } = describeAdminPaymentStatus(payment.status);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <StatusBadge label={label} tone={tone} />
      </div>
      <dl className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Amount</dt>
          <dd>
            <PriceDisplay amountCents={payment.amountCents} currency={payment.currency} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Provider</dt>
          <dd className="text-body text-text-primary">{payment.providerDisplayLabel}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Provider Reference</dt>
          <dd className="text-body text-text-primary">{payment.providerReferenceDisplayValue}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-body text-text-secondary">Linked Order</dt>
          <dd className="text-body text-text-primary">{payment.linkedOrderDisplayId}</dd>
        </div>
      </dl>
      <div className="flex items-center gap-2">
        <Button type="button" onClick={() => onReconcile(payment.id)} disabled={isReconciling} isLoading={isReconciling}>
          Reconcile
        </Button>
        {isReconciling && <span className="text-caption text-text-secondary">Reconciling…</span>}
      </div>
    </div>
  );
}
