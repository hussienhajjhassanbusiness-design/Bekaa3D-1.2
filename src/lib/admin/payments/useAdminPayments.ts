"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { adminOrderKeys } from "@/lib/admin/orders/adminOrdersApi";
import { adminPaymentKeys, adminPaymentsApi } from "./adminPaymentsApi";
import { describeAdminPaymentError } from "./adminPaymentPresentation";
import type { RefundAttemptTracker } from "./refundIdempotency";
import type {
  AdminPaymentDetailDTO,
  AdminPaymentPageDTO,
  AdminPaymentsQueryParams,
  AdminRefundsQueryParams,
  RefundDetailDTO,
  RefundPageDTO,
} from "./adminPaymentTypes";

// #FVS028-ADMIN-PAYMENT-QUERIES (phase 5I)

export function useAdminPayments(params: AdminPaymentsQueryParams) {
  return useQuery<AdminPaymentPageDTO, ApiError>({
    queryKey: adminPaymentKeys.paymentList(params),
    queryFn: () => adminPaymentsApi.listPayments(params),
  });
}

export function useAdminPayment(paymentId: string, options: { enabled?: boolean } = {}) {
  return useQuery<AdminPaymentDetailDTO, ApiError>({
    queryKey: adminPaymentKeys.payment(paymentId),
    queryFn: () => adminPaymentsApi.getPayment(paymentId),
    enabled: options.enabled ?? true,
  });
}

export function useAdminRefunds(params: AdminRefundsQueryParams) {
  return useQuery<RefundPageDTO, ApiError>({
    queryKey: adminPaymentKeys.refundList(params),
    queryFn: () => adminPaymentsApi.listRefunds(params),
  });
}

export function useAdminRefund(refundId: string, options: { enabled?: boolean } = {}) {
  return useQuery<RefundDetailDTO, ApiError>({
    queryKey: adminPaymentKeys.refund(refundId),
    queryFn: () => adminPaymentsApi.getRefund(refundId),
    enabled: options.enabled ?? true,
  });
}

// #FVS028-ADMIN-FINANCIAL-WRITE
//
// One financial write at a time per control: never retried by itself, a
// synchronous ref guard against double submits. A success stores a returned
// RefundDetail in its canonical key and re-reads payments, refunds and
// orders (refunds change the order's status, balances and Refunds rows).
// A refusal re-reads too. With an idempotency tracker, the key survives
// only an UNCERTAIN outcome; any definitive answer retires it.
export type AdminFinancialWriteState = { kind: "idle" } | { kind: "pending" } | { kind: "error"; message: string; error: unknown };

function isRefundDetail(value: unknown): value is RefundDetailDTO {
  return typeof value === "object" && value !== null && "id" in value && "kind" in value && "items" in value;
}

export function useAdminFinancialWrite() {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);
  const [state, setState] = useState<AdminFinancialWriteState>({ kind: "idle" });
  const { mutateAsync } = useMutation({ mutationFn: (call: () => Promise<unknown>) => call(), retry: false });

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: adminPaymentKeys.payments });
    void queryClient.invalidateQueries({ queryKey: adminPaymentKeys.refunds });
    void queryClient.invalidateQueries({ queryKey: adminOrderKeys.root });
  }, [queryClient]);

  const run = useCallback(
    async <T,>(call: () => Promise<T>, tracker?: RefundAttemptTracker): Promise<T | null> => {
      if (inFlight.current) return null;
      inFlight.current = true;
      setState({ kind: "pending" });
      try {
        const result = (await mutateAsync(call)) as T;
        tracker?.retire();
        if (isRefundDetail(result)) queryClient.setQueryData(adminPaymentKeys.refund(result.id), result);
        refresh();
        setState({ kind: "idle" });
        return result;
      } catch (error) {
        const outcome = describeAdminPaymentError(error);
        if (!outcome.uncertain) tracker?.retire();
        if (outcome.refetch) refresh();
        setState({ kind: "error", message: outcome.message, error });
        return null;
      } finally {
        inFlight.current = false;
      }
    },
    [mutateAsync, queryClient, refresh]
  );

  const reset = useCallback(() => setState({ kind: "idle" }), []);
  return { state, run, reset };
}
