import type { ReactNode } from "react";
import type { EntitlementModel } from "@/lib/entitlements/entitlementModel";

export interface EntitlementCardProps {
  entitlement: EntitlementModel;
  // Generic seam — FVS-021 populates this with its own `DownloadButton`
  // once the authorized-download-href contract exists. This component
  // never guesses a download endpoint and never builds a second,
  // temporary download control.
  actionSlot?: ReactNode;
}

// #FVS020-ENTITLEMENT-CARD
//
// Presentational only, no network. The thumbnail (when supplied) is
// decorative (`alt=""`) since the product name is already present as
// visible text right next to it — avoids a duplicate screen-reader
// announcement. Plain <img>, not next/image: the real image host/URL
// format is still an open contract gap
// (FRONTEND-VERTICAL-SLICE-PLAN.md §17's "Image/asset URL format"
// item), same documented constraint as FVS-012/014's own galleries.
export function EntitlementCard({ entitlement, actionSlot }: EntitlementCardProps) {
  return (
    <div className="flex items-center gap-3 border-b border-border-default py-4">
      {entitlement.thumbnailSrc && (
        <img src={entitlement.thumbnailSrc} alt="" className="h-16 w-16 rounded-sm object-cover" />
      )}
      <div className="flex-1">
        <p className="text-body font-semibold text-text-primary">{entitlement.productDisplayName}</p>
        {entitlement.currentVersionLabel && (
          <p className="mt-1 text-caption text-text-secondary">{entitlement.currentVersionLabel}</p>
        )}
      </div>
      {actionSlot && <div>{actionSlot}</div>}
    </div>
  );
}
