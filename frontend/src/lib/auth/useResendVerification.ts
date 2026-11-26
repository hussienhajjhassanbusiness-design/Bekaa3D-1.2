import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

export interface ResendVerificationRequest {
  email: string;
  // Current backend contract (openapi.json ResendVerificationRequest, backend
  // 2dfb27b): required Cloudflare Turnstile token.
  captcha_token: string;
}

export interface ResendVerificationResponse {
  message: string;
}

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/11/12 (confirmed at BATCH 2):
// exact path/body, HTTP 202, enumeration-safe regardless of account
// existence. The response `message` is never read by any caller — same
// safe-message/enumeration-safety rule as useRegister. `retry: false` — a
// write must never auto-retry.
export function useResendVerification() {
  return useMutation({
    mutationFn: (body: ResendVerificationRequest) =>
      apiClient.post<ResendVerificationResponse>("/api/v1/auth/resend-verification", body),
    retry: false,
  });
}
