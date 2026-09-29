"use client";

import { useReadiness } from "@/lib/health/useReadiness";
import { LoadingSpinner } from "./LoadingSpinner";

// FRONTEND-VERTICAL-SLICE-PLAN.md §16/§21, bekaa3d-brand-ui tokens.md §2 —
// not-ready uses the warning token family; unreachable/timeout share the
// danger token family (same visual severity), distinguished from each
// other only by message copy, per the task's own explicit instruction not
// to merge them into identical text.
const NOT_READY_CLASSES = "bg-warning-bg border-l-warning";
const FAILURE_CLASSES = "bg-danger-bg border-l-danger";
const BANNER_BASE_CLASSES = "rounded-md border-l-4 p-4 text-text-primary";

// FVS001-T13b — the UI/accessibility consumer of FVS001-T13a's useReadiness.
// This component deliberately contains NO process.env.NODE_ENV check: an
// internal early-return after calling useReadiness() would still start its
// polling in production (React hooks cannot be conditionally called), so
// whether this component exists in a build at all is decided entirely by
// whether a later composition task mounts it — never by logic in here.
export function BackendUnreachableBanner() {
  const { state, isLoading } = useReadiness();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  switch (state) {
    case "ready":
    case undefined:
      return null;

    case "not-ready":
      return (
        <div role="status" aria-live="polite" className={`${BANNER_BASE_CLASSES} ${NOT_READY_CLASSES}`}>
          <p className="text-body">The backend is reachable but not ready yet.</p>
        </div>
      );

    case "unreachable":
      return (
        <div role="alert" aria-live="assertive" className={`${BANNER_BASE_CLASSES} ${FAILURE_CLASSES}`}>
          <p className="text-body">The backend could not be reached.</p>
        </div>
      );

    case "timeout":
      return (
        <div role="alert" aria-live="assertive" className={`${BANNER_BASE_CLASSES} ${FAILURE_CLASSES}`}>
          <p className="text-body">The backend readiness check timed out.</p>
        </div>
      );
  }
}
