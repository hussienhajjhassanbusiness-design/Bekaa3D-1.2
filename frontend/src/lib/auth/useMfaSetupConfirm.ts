import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// P1-2 — finishes MFA enrolment, upgrading the current session to
// MFA-complete (no second login needed). Returns the ten recovery
// codes exactly once — the caller (MFA setup page) must require an
// explicit "I've saved these" acknowledgment before navigating away.
export interface MfaSetupConfirmRequest {
  code: string;
}

export interface MfaRecoveryCodesResponse {
  recovery_codes: string[];
  generated_at: string;
}

function confirm(request: MfaSetupConfirmRequest): Promise<MfaRecoveryCodesResponse> {
  return apiClient.post<MfaRecoveryCodesResponse>("/api/v1/auth/mfa/setup/confirm", request, { csrf: true });
}

export function useMfaSetupConfirm() {
  return useMutation({
    mutationFn: confirm,
    retry: false,
  });
}
