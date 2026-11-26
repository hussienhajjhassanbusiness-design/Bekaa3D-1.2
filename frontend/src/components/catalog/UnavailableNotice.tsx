import { Icon } from "@/components/ui/Icon";

export interface UnavailableNoticeProps {
  message: string;
}

// Presentational only — receives its copy/state from the parent, never
// infers availability from a missing field and never encodes a backend
// status literal itself. No purchase action lives here; a WhatsApp CTA
// (if applicable for this product) is a sibling the parent renders
// separately.
// Batch 3: Stitch callout (COMPONENT-SPECS §56) in the warning tone.
export function UnavailableNotice({ message }: UnavailableNoticeProps) {
  return (
    <div role="status" className="flex items-start gap-3 rounded-card border border-warning-outline bg-warning-container p-4 text-on-warning-container">
      <Icon name="warning" className="h-5 w-5 shrink-0" />
      <p className="font-body text-body-md">{message}</p>
    </div>
  );
}
