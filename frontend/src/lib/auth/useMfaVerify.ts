import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// P1-2 — finishes an administrator login. No cookie exists yet and no
// CSRF header is sent: challenge_id itself is the credential. Exactly
// one of code/recovery_code must be present (enforced by the caller
// building this request, mirrored server-side). Success is 204 with no
// body; the three session cookies arrive via Set-Cookie and are never
// read here. Calls apiClient directly, never authenticatedRequest or
// adminRequest — MFA endpoints must never be called through the
// refresh-retry wrapper (see authenticatedRequest.ts's own exclusion
// note), and no admin session exists yet at this point anyway.
export interface MfaVerifyRequest {
  challenge_id: string;
  code?: string;
  recovery_code?: string;
}

function verify(request: MfaVerifyRequest): Promise<void> {
  return apiClient.post<void>("/api/v1/auth/mfa/verify", request);
}

export function useMfaVerify() {
  return useMutation({
    mutationFn: verify,
    retry: false,
  });
}
