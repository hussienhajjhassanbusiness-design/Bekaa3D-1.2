"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { orderKeys } from "./orderKeys";
import { ordersApi } from "./ordersApi";
import { describeOrderActionError, type OrderAction, type OrderActionErrorOutcome } from "./orderActionErrors";
import type { OrderDetailReadDTO } from "./orderTypes";

// #FVS031-ORDER-ACTION-MUTATION (phase 5G)
//
// One hook for the three customer order actions. No second order store:
//   - success: the server's own OrderDetailRead is written into the
//     canonical orderKeys.detail(id) entry (nothing is computed locally),
//     then the whole user-scoped orderKeys.root family is invalidated so
//     the history list (status / amount due) and the detail re-read too.
//   - failure: frontend-owned copy (orderActionErrors.ts); a refusal, 404
//     or unknown outcome also re-reads the order family.
//   - never retried by itself (`retry: false`); a synchronous ref guard
//     drops a second submit that lands before React re-renders the
//     disabled control.
export type OrderActionState =
  { kind: "idle" } | { kind: "pending" } | { kind: "success" } | { kind: "error"; outcome: OrderActionErrorOutcome };

type ActionArgs<A extends OrderAction> = A extends "report-problem" ? [message: string] : [];

function run(orderId: string, action: OrderAction, args: unknown[]): Promise<OrderDetailReadDTO> {
  switch (action) {
    case "cancel":
      return ordersApi.cancelOrder(orderId);
    case "confirm-receipt":
      return ordersApi.confirmReceipt(orderId);
    case "report-problem":
      return ordersApi.reportProblem(orderId, String(args[0]));
  }
}

export function useOrderAction<A extends OrderAction>(orderId: string, action: A) {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);
  const [state, setState] = useState<OrderActionState>({ kind: "idle" });

  const { mutateAsync } = useMutation({
    mutationFn: (args: unknown[]) => run(orderId, action, args),
    retry: false,
  });

  const submit = useCallback(
    async (...args: ActionArgs<A>): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setState({ kind: "pending" });
      try {
        const detail = await mutateAsync(args);
        queryClient.setQueryData(orderKeys.detail(orderId), detail);
        void queryClient.invalidateQueries({ queryKey: orderKeys.root });
        setState({ kind: "success" });
        return true;
      } catch (error) {
        const outcome = describeOrderActionError(action, error);
        if (outcome.refetchOrder) {
          void queryClient.invalidateQueries({ queryKey: orderKeys.root });
        }
        setState({ kind: "error", outcome });
        return false;
      } finally {
        inFlight.current = false;
      }
    },
    [action, mutateAsync, orderId, queryClient]
  );

  const reset = useCallback(() => setState({ kind: "idle" }), []);

  return { state, submit, reset };
}
