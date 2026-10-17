import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// Phase 2 auth/account batch — confirmed contract (docs/backend-handoff/
// openapi.json): POST /api/v1/auth/password-reset/request, body {email},
// HTTP 202 always ("Always, whether or not the address is known"), public
// (no cookie, no CSRF header — BACKEND-RESPONSE.md §1.2/P2-6). The
// response `message` is never read by any caller — same enumeration-
// safety rule useRegister/useResendVerification already follow; success
// is the HTTP outcome alone. `retry: false` — a write must never
// auto-retry.
export interface PasswordResetRequestBody {
  email: string;
}

export interface PasswordResetRequestResponse {
  message: string;
}

export function usePasswordResetRequest() {
  return useMutation({
    mutationFn: (body: PasswordResetRequestBody) =>
      apiClient.post<PasswordResetRequestResponse>("/api/v1/auth/password-reset/request", body),
    retry: false,
  });
}
