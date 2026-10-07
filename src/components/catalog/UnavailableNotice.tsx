export interface UnavailableNoticeProps {
  message: string;
}

// Presentational only — receives its copy/state from the parent, never
// infers availability from a missing field and never encodes a backend
// status literal itself. No purchase action lives here; a WhatsApp CTA
// (if applicable for this product) is a sibling the parent renders
// separately.
export function UnavailableNotice({ message }: UnavailableNoticeProps) {
  return (
    <div role="status" className="rounded-md border-l-4 border-l-warning bg-warning-bg p-4 text-text-primary">
      <p className="text-body">{message}</p>
    </div>
  );
}
