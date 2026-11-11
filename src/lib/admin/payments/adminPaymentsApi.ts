import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type {
  ChargebackCreateDTO,
  ChargebackDetailDTO,
  OrderReleaseReadDTO,
  OrderReleaseRequestDTO,
  RecordCaptureReadDTO,
  RecordCaptureRequestDTO,
  AdminPaymentDetailDTO,
  AdminPaymentPageDTO,
  AdminPaymentsQueryParams,
  AdminRefundsQueryParams,
  ManualPaymentConfirmRequestDTO,
  ReconcileQueuedDTO,
  RefundCreateDTO,
  RefundDetailDTO,
  RefundPageDTO,
  RefundReasonRequestDTO,
  RefundSettlementRequestDTO,
} from "./adminPaymentTypes";

// #FVS028-ADMIN-PAYMENTS-API (phase 5I)
//
// Through adminRequest (refresh-once, MFA signal). Writes send X-CSRF-Token.
// Refund create and reissue send the caller's Idempotency-Key (the key is
// captured in the closure, so the shared refresh-and-resend repeats the
// identical request). No financial write is ever retried by itself.

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const enc = encodeURIComponent;

async function listPayments(params: AdminPaymentsQueryParams): Promise<AdminPaymentPageDTO> {
  return adminRequest(() => apiClient.get<AdminPaymentPageDTO>(`/api/v1/admin/payments${query({ ...params })}`));
}

async function getPayment(paymentId: string): Promise<AdminPaymentDetailDTO> {
  return adminRequest(() => apiClient.get<AdminPaymentDetailDTO>(`/api/v1/admin/payments/${enc(paymentId)}`));
}

async function reconcilePayment(paymentId: string): Promise<ReconcileQueuedDTO> {
  return adminRequest(() =>
    apiClient.post<ReconcileQueuedDTO>(`/api/v1/admin/payments/${enc(paymentId)}/reconcile`, undefined, { csrf: true })
  );
}

async function confirmPayment(paymentId: string, body: ManualPaymentConfirmRequestDTO): Promise<unknown> {
  return adminRequest(() => apiClient.post(`/api/v1/admin/payments/${enc(paymentId)}/confirm`, body, { csrf: true }));
}

async function listRefunds(params: AdminRefundsQueryParams): Promise<RefundPageDTO> {
  return adminRequest(() => apiClient.get<RefundPageDTO>(`/api/v1/admin/refunds${query({ ...params })}`));
}

async function getRefund(refundId: string): Promise<RefundDetailDTO> {
  return adminRequest(() => apiClient.get<RefundDetailDTO>(`/api/v1/admin/refunds/${enc(refundId)}`));
}

async function createRefund(orderId: string, body: RefundCreateDTO, idempotencyKey: string): Promise<RefundDetailDTO> {
  return adminRequest(() =>
    apiClient.post<RefundDetailDTO>(`/api/v1/admin/orders/${enc(orderId)}/refunds`, body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
    })
  );
}

async function settleRefund(refundId: string, body: RefundSettlementRequestDTO): Promise<RefundDetailDTO> {
  return adminRequest(() =>
    apiClient.post<RefundDetailDTO>(`/api/v1/admin/refunds/${enc(refundId)}/settle`, body, { csrf: true })
  );
}

async function failRefund(refundId: string, body: RefundReasonRequestDTO): Promise<RefundDetailDTO> {
  return adminRequest(() => apiClient.post<RefundDetailDTO>(`/api/v1/admin/refunds/${enc(refundId)}/fail`, body, { csrf: true }));
}

async function voidRefund(refundId: string, body: RefundReasonRequestDTO): Promise<RefundDetailDTO> {
  return adminRequest(() => apiClient.post<RefundDetailDTO>(`/api/v1/admin/refunds/${enc(refundId)}/void`, body, { csrf: true }));
}

async function reissueRefund(refundId: string, idempotencyKey: string): Promise<RefundDetailDTO> {
  return adminRequest(() =>
    apiClient.post<RefundDetailDTO>(`/api/v1/admin/refunds/${enc(refundId)}/reissue`, undefined, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
    })
  );
}

// Phase 6A: manual release, late capture, chargeback create.
async function releaseOrder(orderId: string, body: OrderReleaseRequestDTO): Promise<OrderReleaseReadDTO> {
  return adminRequest(() => apiClient.post<OrderReleaseReadDTO>(`/api/v1/admin/orders/${enc(orderId)}/release`, body, { csrf: true }));
}

async function recordCapture(paymentId: string, body: RecordCaptureRequestDTO, idempotencyKey: string): Promise<RecordCaptureReadDTO> {
  return adminRequest(() =>
    apiClient.post<RecordCaptureReadDTO>(`/api/v1/admin/payments/${enc(paymentId)}/record-capture`, body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
    })
  );
}

async function createChargeback(orderId: string, body: ChargebackCreateDTO, idempotencyKey: string): Promise<ChargebackDetailDTO> {
  return adminRequest(() =>
    apiClient.post<ChargebackDetailDTO>(`/api/v1/admin/orders/${enc(orderId)}/chargebacks`, body, {
      csrf: true,
      headers: { "Idempotency-Key": idempotencyKey },
    })
  );
}

export const adminPaymentsApi = {
  releaseOrder,
  recordCapture,
  createChargeback,
  listPayments,
  getPayment,
  reconcilePayment,
  confirmPayment,
  listRefunds,
  getRefund,
  createRefund,
  settleRefund,
  failRefund,
  voidRefund,
  reissueRefund,
};

// Under the user-scoped ["admin"] root (dropped on logout / user switch).
export const adminPaymentKeys = {
  payments: ["admin", "payments"] as const,
  paymentList: (params: AdminPaymentsQueryParams) => [...adminPaymentKeys.payments, "list", params] as const,
  payment: (paymentId: string) => [...adminPaymentKeys.payments, "detail", paymentId] as const,
  refunds: ["admin", "refunds"] as const,
  refundList: (params: AdminRefundsQueryParams) => [...adminPaymentKeys.refunds, "list", params] as const,
  refund: (refundId: string) => [...adminPaymentKeys.refunds, "detail", refundId] as const,
};
