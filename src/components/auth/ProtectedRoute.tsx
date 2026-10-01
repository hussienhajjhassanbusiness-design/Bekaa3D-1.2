"use client";

// FVS-003-IMPLEMENTATION-PLAN.md §9/Part D (confirmed BATCH 3B) — gates
// rendering on the REAL AuthProvider interface, never a second,
// independently-tracked auth state. Protected children are never rendered
// before auth resolves: while loading, only the LoadingSpinner renders;
// while anonymous, nothing renders and the user is redirected to
// /login?returnTo=<current path>, preserving the pathname and query
// string (never the origin) via the existing returnTo builder.
//
// Invariant owned by callers, not enforced here: ProtectedRoute must never
// wrap /login itself, or an anonymous visit to /login would redirect back
// to /login in a loop.
import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const query = searchParams.toString();
  const currentPath = query ? `${pathname}?${query}` : pathname;

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace(buildLoginRedirectPath(currentPath));
    }
  }, [isLoading, isAuthenticated, currentPath, router]);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
