import { useEffect, useReducer } from "react";

export interface UseCooldownResult {
  remainingSeconds: number;
  isActive: boolean;
}

// FVS-002-IMPLEMENTATION-PLAN.md §11 — derives remaining time from an
// ABSOLUTE deadline (never a decrementing counter), so a throttled/
// backgrounded timer gap corrects itself on the next tick instead of
// drifting. One small hook, local to this feature — no general-purpose
// countdown framework.
function computeRemainingSeconds(deadline: number | undefined): number {
  if (deadline === undefined) {
    return 0;
  }
  return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

export function useCooldown(deadline: number | undefined): UseCooldownResult {
  // remainingSeconds is deliberately NOT stored in its own state slice —
  // it is derived fresh every render from `deadline` and the real clock,
  // which is what makes a throttled/background gap self-correct instead of
  // drifting. `tick` exists only to force a re-render once per second while
  // the deadline is active; the effect below only ever calls it from the
  // interval's own callback (an external-system update), never
  // synchronously from the effect body itself.
  const [, tick] = useReducer((count: number) => count + 1, 0);

  useEffect(() => {
    if (deadline === undefined) {
      return;
    }

    const intervalId = setInterval(() => {
      if (computeRemainingSeconds(deadline) <= 0) {
        clearInterval(intervalId);
      }
      tick();
    }, 1000);

    return () => clearInterval(intervalId);
  }, [deadline]);

  const remainingSeconds = computeRemainingSeconds(deadline);
  return { remainingSeconds, isActive: remainingSeconds > 0 };
}
