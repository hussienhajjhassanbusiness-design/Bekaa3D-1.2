export interface SuccessReceiptProps {
  message: string;
}

// #SHARED-SUCCESS-RECEIPT
//
// Generalized from FVS-015's own BYI-only component: generic, safe
// confirmation for any guest-submission flow (BYI, Contact, future
// ones). `message` is required — no default is baked in here, since a
// default would inevitably be flavored toward one caller's domain (the
// original BYI version's default said "idea", which would have been
// wrong for Contact). No internal database id, storage key, attachment
// URL, captcha proof, or internal status is ever exposed — none of
// that is a backend-confirmed public-safe field for any consumer yet.
export function SuccessReceipt({ message }: SuccessReceiptProps) {
  return (
    <div role="status" className="rounded-md border-l-4 border-l-success bg-success-bg p-4 text-text-primary">
      <p className="text-body">{message}</p>
    </div>
  );
}
