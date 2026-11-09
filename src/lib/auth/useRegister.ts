import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

export interface RegisterRequest {
  email: string;
  password: string;
  // Current backend contract (openapi.json RegisterRequest, backend 2dfb27b,
  // ADR-025/026): required Cloudflare Turnstile token, max 2048 chars.
  captcha_token: string;
}

export interface RegisterResponse {
  message: string;
}

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/2/5/6/15 (confirmed at BATCH 2):
// exact path/body, HTTP 202 success. The `message` field is never read by
// any caller — enumeration-safety and the safe-message rule both forbid
// rendering it; success is the HTTP outcome alone (matches useReadiness's
// existing pattern). `retry: false` — a write must never auto-retry (§6/§7).
export function useRegister() {
  return useMutation({
    mutationFn: (body: RegisterRequest) => apiClient.post<RegisterResponse>("/api/v1/auth/register", body),
    retry: false,
  });
}
