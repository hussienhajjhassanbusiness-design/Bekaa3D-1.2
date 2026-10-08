// #FVS027 — honest copy only. No fake percentage/progress bar — a
// spinner never implies a measurable fraction of completion, and the
// copy never implies the provider has already approved anything.
// Deliberately has no `role="status"`/live region of its own —
// PaymentResultView owns the ONE aria-live region wrapping whichever
// state renders, avoiding nested/duplicate announcements.
export function PaymentPendingState() {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <svg aria-hidden="true" className="h-8 w-8 animate-spin motion-reduce:animate-none text-brand-dark-green" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p className="text-body text-text-primary">Confirming your payment…</p>
      <p className="text-caption text-text-secondary">Please don&apos;t close this page.</p>
    </div>
  );
}
