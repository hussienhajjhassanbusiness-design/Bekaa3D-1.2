// #PHASE3-ADMIN-REQUEST
//
// Every admin data hook (settings/customers/reference-data/products/
// images) wraps its apiClient call through this instead of calling
// authenticatedRequest directly. Two concerns are handled, in order:
//
// 1. The ordinary AUTH_REQUIRED -> refresh -> retry-once rule
//    (authenticatedRequest, unchanged, reused as-is).
// 2. The admin-specific rule (BACKEND-RESPONSE.md P1-1 Notes): a
//    401 MFA_REQUIRED from ANY admin call means this admin's MFA
//    enrolment is incomplete — never retried/refreshed (it isn't an
//    AUTH_REQUIRED), instead the shared mfaRequiredSignal is notified
//    so AdminGuard (the one place that owns navigation) can redirect to
//    MFA setup. The original error still propagates to the caller
//    unchanged, so a hook's own error UI still has a real error to show
//    if the redirect is mid-flight.
import type { ApiError } from "@/lib/api/ApiError";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import { notifyMfaRequired } from "./mfaRequiredSignal";

export function isMfaRequiredError(error: unknown): error is ApiError {
  return (
    typeof error === "object" &&
    error !== null &&
    "kind" in error &&
    (error as ApiError).kind === "http" &&
    (error as ApiError).status === 401 &&
    (error as ApiError).code === "MFA_REQUIRED"
  );
}

export async function adminRequest<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await authenticatedRequest(call);
  } catch (error) {
    if (isMfaRequiredError(error)) {
      notifyMfaRequired();
    }
    throw error;
  }
}
