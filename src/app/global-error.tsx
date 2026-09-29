"use client"; // Error boundaries must be Client Components

import "./globals.css";

// Last-resort root-level fallback (FRONTEND-VERTICAL-SLICE-PLAN.md §17,
// category A) — only fires when something breaks badly enough to escape
// error.tsx itself (e.g. a failure in the root layout). Deliberately does
// NOT use AppLayout/Header/Footer: this must stay independently survivable
// even if those components (or whatever broke the root layout) are
// themselves implicated in the failure. Next.js also does not carry the
// app's normal global styles into this file automatically — it renders its
// own separate document — so globals.css is imported directly here to get
// real token-driven styling instead of raw hex or a bare unstyled page.
//
// Category A only — never route ApiError/RFC 9457/network/health failures
// here; see error.tsx for the same rule with more detail.
export default function GlobalError({
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-base px-4 text-center">
          <h1 className="text-h1 font-bold text-text-primary">Something went wrong</h1>
          <p className="text-body text-text-secondary">
            An unexpected error occurred. Please try again.
          </p>
          <button
            type="button"
            onClick={() => retry()}
            className="rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
