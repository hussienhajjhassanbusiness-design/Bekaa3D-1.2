"use client";

// #PHASE3-ADMIN-GUARD (P1-1)
//
// Same shape as src/components/auth/ProtectedRoute.tsx (loading/
// confirmed-anonymous/isError handling, same #ARCHITECTURE-CANONICAL-
// AUTH-QUERY discipline: a genuine transport failure is never collapsed
// into "not admin"), plus two admin-specific rules this slice owns:
//
// 1. role !== "admin" renders the real NotFoundContent — identical to
//    what a nonexistent route shows, never an "admin area exists here,
//    access denied" message. This is UX only: the backend
//    independently answers every /api/v1/admin/* call with its own
//    404/401 regardless of what this component renders (bekaa3d-api-
//    contract: hiding is never authorization).
// 2. Subscribes to mfaRequiredSignal (src/lib/admin/mfaRequiredSignal.ts)
//    for the lifetime of the admin shell: any admin data hook that
//    catches a 401 MFA_REQUIRED (via adminRequest) notifies this
//    signal, and this is the one place that turns it into a redirect
//    to /admin/mfa/setup — never duplicated per-hook.
import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { onMfaRequired } from "@/lib/admin/mfaRequiredSignal";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { Alert } from "@/components/feedback/Alert";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

const TRANSPORT_ERROR_MESSAGE = "We couldn't verify your session. Please try again.";

export function AdminGuard({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, isLoading, isError } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const confirmedAnonymous = !isLoading && !isAuthenticated && !isError;
  const isAdmin = isAuthenticated && user?.role === "admin";

  useEffect(() => {
    if (confirmedAnonymous) {
      router.replace(buildLoginRedirectPath(pathname));
    }
  }, [confirmedAnonymous, pathname, router]);

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    return onMfaRequired(() => {
      router.push("/admin/mfa/setup");
    });
  }, [isAdmin, router]);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (confirmedAnonymous) {
    return null;
  }

  if (isError) {
    return <Alert variant="error" message={TRANSPORT_ERROR_MESSAGE} />;
  }

  if (!isAdmin) {
    return <NotFoundContent />;
  }

  return <>{children}</>;
}
