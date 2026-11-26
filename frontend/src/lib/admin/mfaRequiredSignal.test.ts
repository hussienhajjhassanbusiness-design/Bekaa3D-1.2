import { describe, it, expect, vi } from "vitest";
import { notifyMfaRequired, onMfaRequired } from "./mfaRequiredSignal";

// Phase 3 — P1-1/P1-2: an admin whose MFA enrolment is incomplete gets
// role: "admin" from /me but every /api/v1/admin/* call answers
// 401 MFA_REQUIRED. This in-memory pub/sub lets any admin data hook
// (settings, customers, reference data, products, images) notify a single
// shared subscriber (AdminGuard) to redirect to MFA setup, without each
// hook needing its own router reference. Deliberately NOT cross-tab (no
// BroadcastChannel) — this is a same-render-tree, same-tab signal only.
describe("mfaRequiredSignal", () => {
  it("calls every subscribed listener when notifyMfaRequired is called", () => {
    const listenerA = vi.fn();
    const listenerB = vi.fn();
    const unsubscribeA = onMfaRequired(listenerA);
    const unsubscribeB = onMfaRequired(listenerB);

    notifyMfaRequired();

    expect(listenerA).toHaveBeenCalledTimes(1);
    expect(listenerB).toHaveBeenCalledTimes(1);

    unsubscribeA();
    unsubscribeB();
  });

  it("stops calling a listener once it has unsubscribed", () => {
    const listener = vi.fn();
    const unsubscribe = onMfaRequired(listener);
    unsubscribe();

    notifyMfaRequired();

    expect(listener).not.toHaveBeenCalled();
  });

  it("does nothing when there are no subscribers", () => {
    expect(() => notifyMfaRequired()).not.toThrow();
  });
});
