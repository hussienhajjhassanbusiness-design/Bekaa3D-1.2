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
export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="en">
      <body>
        {/* Batch 11: Stitch tokens only, no shared components, so this
            fallback stays independent of whatever failed. It replaces the
            root layout, so it supplies its own main landmark. */}
        <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-margin-mobile text-center">
          <h1 className="font-headline text-headline-lg text-on-surface">Something went wrong</h1>
          <p className="max-w-md text-body-md text-on-surface-variant">
            An unexpected error occurred. Please try again.
          </p>
          <button
            type="button"
            onClick={() => retry()}
            className="mt-4 inline-flex min-h-11 items-center justify-center rounded-control bg-primary px-6 py-2.5 font-label text-label-caps uppercase leading-4 text-on-primary transition-colors duration-200 hover:bg-primary-container motion-reduce:transition-none"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
