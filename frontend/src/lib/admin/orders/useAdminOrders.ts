"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api/ApiError";
import { adminOrderKeys, adminOrdersApi } from "./adminOrdersApi";
import { describeAdminOrderError } from "./adminOrderPresentation";
import type {
  AdminOrderDetailDTO,
  AdminOrderPageDTO,
  AdminOrdersQueryParams,
  StlDeliveriesQueryParams,
  StlDeliveryPageDTO,
} from "./adminOrderTypes";

// #FVS030-ADMIN-ORDER-QUERIES (phase 5H)

export function useAdminOrders(params: AdminOrdersQueryParams) {
  return useQuery<AdminOrderPageDTO, ApiError>({
    queryKey: adminOrderKeys.list(params),
    queryFn: () => adminOrdersApi.listOrders(params),
  });
}

export function useAdminOrder(orderId: string, options: { enabled?: boolean } = {}) {
  return useQuery<AdminOrderDetailDTO, ApiError>({
    queryKey: adminOrderKeys.detail(orderId),
    queryFn: () => adminOrdersApi.getOrder(orderId),
    enabled: options.enabled ?? true,
  });
}

export function useStlDeliveries(params: StlDeliveriesQueryParams) {
  return useQuery<StlDeliveryPageDTO, ApiError>({
    queryKey: adminOrderKeys.stl(params),
    queryFn: () => adminOrdersApi.listStlDeliveries(params),
  });
}

// #FVS030-ADMIN-ORDER-WRITE
//
// One write at a time per control (the STL queue shares one across rows). Every admin order write answers with
// the full AdminOrderDetail: it is written into the canonical
// adminOrderKeys.detail(id) entry (nothing computed locally) and the whole
// admin order family (queue, STL deliveries, detail) is re-read. A refusal
// re-reads too, so the screen shows the server's current state. Never
// retried by itself; a synchronous ref guard drops a double submit.
export type AdminOrderWriteState = { kind: "idle" } | { kind: "pending" } | { kind: "error"; message: string };

export function useAdminOrderWrite() {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);
  const [state, setState] = useState<AdminOrderWriteState>({ kind: "idle" });
  const { mutateAsync } = useMutation({
    mutationFn: (call: () => Promise<AdminOrderDetailDTO>) => call(),
    retry: false,
  });

  const run = useCallback(
    async (call: () => Promise<AdminOrderDetailDTO>): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setState({ kind: "pending" });
      try {
        const detail = await mutateAsync(call);
        queryClient.setQueryData(adminOrderKeys.detail(detail.id), detail);
        void queryClient.invalidateQueries({ queryKey: adminOrderKeys.root });
        setState({ kind: "idle" });
        return true;
      } catch (error) {
        const outcome = describeAdminOrderError(error);
        if (outcome.refetchOrder) {
          void queryClient.invalidateQueries({ queryKey: adminOrderKeys.root });
        }
        setState({ kind: "error", message: outcome.message });
        return false;
      } finally {
        inFlight.current = false;
      }
    },
    [mutateAsync, queryClient]
  );

  const reset = useCallback(() => setState({ kind: "idle" }), []);
  return { state, run, reset };
}
