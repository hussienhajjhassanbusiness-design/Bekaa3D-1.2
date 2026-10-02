"use client";

// FVS-003-IMPLEMENTATION-PLAN.md §9/Part D (confirmed BATCH 3B) — gates
// rendering on the REAL AuthProvider interface, never a second,
// independently-tracked auth state. Protected children are never rendered
// before auth resolves: while loading, only the LoadingSpinner renders;
// while CONFIRMED anonymous, nothing renders and the user is redirected to
// /login?returnTo=<current path>, preserving the pathname and query
// string (never the origin) via the existing returnTo builder.
//
// #ARCHITECTURE-CANONICAL-AUTH-QUERY — a genuine transport/server failure
// (isError:true) is never treated as confirmed-anonymous: redirecting here
// would bounce a possibly-still-authenticated customer to /login on a
// transient network blip (a real cross-slice defect found and fixed at
// FVS-006 — see authSession.ts/AuthProvider.tsx). On isError, children
// render anyway; it is the individual page's job (via useAuth().isError)
// to show its own retryable error instead of whatever authenticated
// content it would normally render. The real security boundary is always
// each page's own API calls, which independently 401 if the session truly
// isn't valid.
//
// Invariant owned by callers, not enforced here: ProtectedRoute must never
// wrap /login itself, or an anonymous visit to /login would redirect back
// to /login in a loop.
import { Suspense, useEffect, type ReactNode } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

// useSearchParams() opts any page using it out of static prerendering
// unless wrapped in Suspense (Next.js App Router requirement) — wrapped
// once here so every current/future ProtectedRoute consumer gets this for
// free, rather than each page remembering its own Suspense boundary (the
// same requirement login/page.tsx satisfies for its own direct
// useSearchParams() call). The fallback is never visible in practice,
// since this value is available synchronously on the client.
export function ProtectedRoute({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ProtectedRouteInner>{children}</ProtectedRouteInner>
    </Suspense>
  );
}

function ProtectedRouteInner({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, isError } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const query = searchParams.toString();
  const currentPath = query ? `${pathname}?${query}` : pathname;

  const confirmedAnonymous = !isLoading && !isAuthenticated && !isError;

  useEffect(() => {
    if (confirmedAnonymous) {
      router.replace(buildLoginRedirectPath(currentPath));
    }
  }, [confirmedAnonymous, currentPath, router]);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (confirmedAnonymous) {
    return null;
  }

  return <>{children}</>;
}
