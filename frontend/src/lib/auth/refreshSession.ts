// FVS-003-IMPLEMENTATION-PLAN.md §7 (confirmed BATCH 3A) — the real,
// auth-domain refresh coordinator. Layers two mechanisms:
//   1. Same-tab single-flight — T06's unmodified generic primitive.
//   2. Cross-tab mutual exclusion — a named Web Lock (navigator.locks),
//      backend-mandated because simultaneous refresh-token rotation
//      across tabs can trigger reuse detection and revoke the whole
//      session. Inside the lock, the session is re-checked via GET /me
//      before refreshing, so a second tab that acquires the lock after a
//      first tab already refreshed does not rotate the token a second
//      time in a row.
//
// Never recursive: this module calls `apiClient` directly for both /me and
// /refresh — never through `authenticatedRequest` (src/lib/auth/
// authenticatedRequest.ts), which is what would create a refresh-triggers-
// refresh cycle. Any failure, regardless of status/code, resolves `false`
// — callers never need to branch on *why* a refresh failed.
import { apiClient } from "@/lib/api/apiClient";
import { createSingleFlight } from "./singleFlight";

export const REFRESH_LOCK_NAME = "bekaa3d-refresh";
const ME_PATH = "/api/v1/me";
const REFRESH_PATH = "/api/v1/auth/refresh";

async function isSessionAlreadyValid(): Promise<boolean> {
  try {
    await apiClient.get(ME_PATH);
    return true;
  } catch {
    return false;
  }
}

async function performRefresh(): Promise<void> {
  await apiClient.post(REFRESH_PATH, undefined, { csrf: true });
}

async function coordinateAcrossTabs(): Promise<void> {
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  if (!locks) {
    // No Web Locks support: same-tab single-flight (below) is still in
    // effect; this is a documented reduction to single-tab-strength
    // guarantees, not a silently invented cross-tab mechanism.
    await performRefresh();
    return;
  }

  await locks.request(REFRESH_LOCK_NAME, async () => {
    const alreadyValid = await isSessionAlreadyValid();
    if (alreadyValid) {
      return;
    }
    await performRefresh();
  });
}

const refreshOnce = createSingleFlight(coordinateAcrossTabs);

// Resolves `true` on success, `false` on any failure — never throws, never
// retries internally. Exactly one refresh attempt per call.
export async function refreshSession(): Promise<boolean> {
  try {
    await refreshOnce();
    return true;
  } catch {
    return false;
  }
}
