"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import { Button } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";

// Category A ONLY (FRONTEND-VERTICAL-SLICE-PLAN.md §17): unexpected
// React/render/runtime failures caught by Next.js's own App Router segment
// boundary. This must NEVER become the handler for ApiError, RFC 9457
// problem responses, network failures, or backend-readiness state — those
// are expected, recoverable application states (handled by
// BackendUnreachableBanner, §17 categories B/C), not a crash. Do not import
// ApiError, TanStack Query, fetch, or anything backend-related here.
//
// Renders bare content only — a normal segment error.tsx replaces just its
// own segment's children, not any layout above it (unlike global-error.tsx,
// which explicitly replaces the root layout and must define its own
// <html>/<body>). The root layout's AppLayout/Header/Footer shell
// (FVS001-T14) remains rendered around this fallback automatically.
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
    // scope beyond this). Phase 6F: a production build does not write the
    // raw error to the visitor's console; server-side failures keep their
    // `digest` in the server logs (docs/setup/production-readiness.md).
    if (process.env.NODE_ENV !== "production") {
      console.error(error);
    }
  }, [error]);

  return (
    // Batch 11: same centred composition as NotFoundContent (error glyph).
    <div className="mx-auto flex w-full max-w-xl flex-col items-center px-margin-mobile py-16 text-center tablet:py-24">
      <div className="flex h-24 w-24 items-center justify-center rounded-full bg-error-container">
        <Icon name="error" className="h-12 w-12 text-on-error-container" strokeWidth={1.5} />
      </div>
      <h1 className="mt-6 font-headline text-headline-lg text-on-surface">Something went wrong</h1>
      <p className="mt-3 text-body-md text-on-surface-variant">
        An unexpected error occurred while rendering this page.
      </p>
      <Button type="button" onClick={() => retry()} className="mt-8">
        Try again
      </Button>
    </div>
  );
}
