import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/apiClient";

// Phase 2 auth/account batch — confirmed contract (docs/backend-handoff/
// openapi.json): POST /api/v1/auth/password-reset/confirm, body
// {token, new_password}, HTTP 204 with no body on success, public (no
// cookie, no CSRF header — BACKEND-RESPONSE.md §1.2/P2-6). A successful
// reset revokes every session for the account and does NOT establish a
// new one — this hook never touches the ["auth","session"] query and
// never navigates; the caller (the /reset-password page) owns sending
// the user to /login.
export interface PasswordResetConfirmBody {
  token: string;
  new_password: string;
}

export function usePasswordResetConfirm() {
  return useMutation({
    mutationFn: (body: PasswordResetConfirmBody) => apiClient.post<undefined>("/api/v1/auth/password-reset/confirm", body),
    retry: false,
  });
}
