export interface SuccessReceiptProps {
  message?: string;
}

const DEFAULT_MESSAGE = "Thanks! We've received your idea and will be in touch soon.";

// Safe, generic confirmation only. No internal database id, storage
// key, attachment URL, captcha proof, or internal status is exposed —
// none of that is a backend-confirmed public-safe field yet
// (FVS-015-IMPLEMENTATION-PLAN.md §1). A future adapter may supply a
// confirmed public-safe reference number as `message`; this component
// never fabricates one itself.
export function SuccessReceipt({ message = DEFAULT_MESSAGE }: SuccessReceiptProps) {
  return (
    <div role="status" className="rounded-md border-l-4 border-l-success bg-success-bg p-4 text-text-primary">
      <p className="text-body">{message}</p>
    </div>
  );
}
