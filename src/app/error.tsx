"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";

// Category A ONLY (FRONTEND-VERTICAL-SLICE-PLAN.md §17): unexpected
// React/render/runtime failures caught by Next.js's own App Router segment
// boundary. This must NEVER become the handler for ApiError, RFC 9457
// problem responses, network failures, or backend-readiness state — those
// are expected, recoverable application states (handled by
// BackendUnreachableBanner, §17 categories B/C), not a crash. Do not import
// ApiError, TanStack Query, fetch, or anything backend-related here.
//
// Composes AppLayout/Header/Footer itself (matching FVS001-T06's page.tsx/
// not-found.tsx pattern) because AppLayout isn't hoisted into the root
// layout yet — that's FVS001-T14's job. Without this, a render failure
// would drop the header/footer chrome entirely instead of showing a
// consistent, branded fallback.
export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    // Dev-console-only diagnostic — never rendered to the user. No external
    // logging dependency; see T07 scope (logging infrastructure is out of
    // scope beyond this).
    console.error(error);
  }, [error]);

  return (
    <AppLayout header={<Header />} footer={<Footer />}>
      <h1 className="text-h1 font-bold text-text-primary">Something went wrong</h1>
      <p className="text-body text-text-secondary">
        An unexpected error occurred while rendering this page.
      </p>
      <button
        type="button"
        onClick={() => retry()}
        className="rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand"
      >
        Try again
      </button>
    </AppLayout>
  );
}
