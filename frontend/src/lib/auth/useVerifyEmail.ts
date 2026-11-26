import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

export interface VerifyEmailRequest {
  token: string;
}

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/8/9/10 (confirmed at BATCH 2):
// exact path/body, 204 success. apiClient resolves `undefined` for an
// empty/unparseable 2xx body already (apiClient.ts) — no response body is
// required or read here. `retry: false` — the token is single-use; an
// automatic retry after a failure must never fire a second request.
export function useVerifyEmail() {
  return useMutation({
    mutationFn: (body: VerifyEmailRequest) => apiClient.post<void>("/api/v1/auth/verify-email", body),
    retry: false,
  });
}
