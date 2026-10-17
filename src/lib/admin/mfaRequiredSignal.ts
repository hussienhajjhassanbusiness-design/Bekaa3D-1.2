// Phase 3 — P1-1/P1-2: an admin whose MFA enrolment is incomplete gets
// role: "admin" from /me but every /api/v1/admin/* call answers
// 401 MFA_REQUIRED. This in-memory pub/sub lets any admin data hook
// notify a single shared subscriber (AdminGuard) to redirect to MFA
// setup, without each hook needing its own router reference.
// Deliberately NOT cross-tab (no BroadcastChannel, unlike
// src/lib/auth/crossTabSignal.ts) — this is a same-render-tree signal.

export type MfaRequiredListener = () => void;

const listeners = new Set<MfaRequiredListener>();

export function notifyMfaRequired(): void {
  for (const listener of listeners) {
    listener();
  }
}

export function onMfaRequired(listener: MfaRequiredListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
