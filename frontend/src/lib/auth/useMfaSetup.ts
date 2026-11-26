import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// P1-2 — begins MFA enrolment for the already-signed-in administrator.
// `secret`/`otpauth_uri` are returned exactly once and are sensitive —
// this hook makes no storage claim; the caller (MFA setup page) must
// keep them in memory only, never log/persist them.
export interface MfaSetupRequest {
  current_password: string;
}

export interface MfaSetupResponse {
  secret: string;
  otpauth_uri: string;
  issuer: string;
  account_name: string;
}

function setup(request: MfaSetupRequest): Promise<MfaSetupResponse> {
  return apiClient.post<MfaSetupResponse>("/api/v1/auth/mfa/setup", request, { csrf: true });
}

export function useMfaSetup() {
  return useMutation({
    mutationFn: setup,
    retry: false,
  });
}
