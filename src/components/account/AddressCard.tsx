import { useId, type ReactNode } from "react";
import { Button } from "@/components/forms/Button";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Icon, type IconName } from "@/components/ui/Icon";
import { governorateLabel, type AddressModel } from "@/lib/addresses/addressModel";

export interface AddressCardProps {
  address: AddressModel;
  onEdit: (addressId: string) => void;
  // A request only — the container confirms before anything is deleted.
  onDelete: (addressId: string) => void;
  onSetDefault: (addressId: string) => void;
  isSettingDefault?: boolean;
  actionsDisabled?: boolean;
}

// #FVS023-ADDRESS-CARD
//
// Presentational only — no network. One saved address from the real
// AddressRead. "Default" is visible text, never colour alone. Action
// buttons carry the label in their accessible name ("Edit Home") so
// screen-reader users can tell several cards' buttons apart; the visible
// text stays first in the name (WCAG 2.5.3 label-in-name).
// #ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE — no zone/rate/fee, ever.
export function AddressCard({
  address,
  onEdit,
  onDelete,
  onSetDefault,
  isSettingDefault = false,
  actionsDisabled = false,
}: AddressCardProps) {
  const headingId = useId();
  const streetLine = [address.street, address.area].filter((part): part is string => Boolean(part)).join(", ");
  const cityLine = `${address.city}, ${governorateLabel(address.governorate)}`;

  return (
    <article
      aria-labelledby={headingId}
      className={`flex h-full flex-col gap-5 rounded-card border bg-surface-container-lowest p-6 shadow-sm ${
        address.isDefault ? "border-primary/60 ring-1 ring-primary/20" : "border-outline-variant/30"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 id={headingId} className="min-w-0 break-words font-headline text-headline-md text-on-surface">
          {address.label}
        </h2>
        {address.isDefault && <StatusBadge label="Default" tone="positive" />}
      </div>

      <dl className="flex flex-1 flex-col gap-4 break-words">
        <AddressDetail icon="person" term="Recipient">
          <p>{address.recipientName}</p>
        </AddressDetail>
        <AddressDetail icon="call" term="Phone">
          {/* Phone numbers stay left-to-right and on one line where they fit. */}
          <p dir="ltr" className="tabular-nums">
            {address.phone}
          </p>
        </AddressDetail>
        <AddressDetail icon="location-on" term="Location">
          {streetLine && <p>{streetLine}</p>}
          <p>{cityLine}</p>
        </AddressDetail>
        <div className="rounded-lg bg-surface-container-low p-3">
          <dt className={TERM_CLASSES}>Landmark notes</dt>
          <dd className="mt-1 whitespace-pre-line text-body-md text-on-surface-variant">{address.landmarkNotes}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-center gap-2 border-t border-outline-variant/30 pt-4">
        <Button
          type="button"
          variant="outline"
          aria-label={`Edit ${address.label}`}
          disabled={actionsDisabled}
          onClick={() => onEdit(address.id)}
        >
          <Icon name="edit" className="h-4 w-4" />
          Edit
        </Button>
        {!address.isDefault && (
          <Button
            type="button"
            variant="secondary"
            aria-label={`Set as default: ${address.label}`}
            disabled={actionsDisabled}
            isLoading={isSettingDefault}
            onClick={() => onSetDefault(address.id)}
          >
            Set as default
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          aria-label={`Delete ${address.label}`}
          disabled={actionsDisabled}
          onClick={() => onDelete(address.id)}
        >
          <Icon name="delete" className="h-4 w-4" />
          Delete
        </Button>
      </div>
    </article>
  );
}

const TERM_CLASSES = "font-label text-label-sm uppercase tracking-widest text-on-surface-variant";

function AddressDetail({ icon, term, children }: { icon: IconName; term: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <Icon name={icon} className="mt-0.5 h-5 w-5 text-primary" />
      <div className="min-w-0">
        <dt className={TERM_CLASSES}>{term}</dt>
        <dd className="mt-1 text-body-md text-on-surface">{children}</dd>
      </div>
    </div>
  );
}
