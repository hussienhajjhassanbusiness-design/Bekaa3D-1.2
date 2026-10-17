import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";
import type { MfaRecoveryCodesResponse } from "./useMfaSetupConfirm";

// P1-2 — invalidates all existing recovery codes and issues ten new
// ones. Same request shape as useMfaSetup (current_password + CSRF),
// same once-only recovery-codes response shape as useMfaSetupConfirm.
export interface MfaRecoveryRegenerateRequest {
  current_password: string;
}

function regenerate(request: MfaRecoveryRegenerateRequest): Promise<MfaRecoveryCodesResponse> {
  return apiClient.post<MfaRecoveryCodesResponse>("/api/v1/auth/mfa/recovery-codes/regenerate", request, {
    csrf: true,
  });
}

export function useMfaRecoveryRegenerate() {
  return useMutation({
    mutationFn: regenerate,
    retry: false,
  });
}
