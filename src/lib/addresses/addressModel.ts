import type { AddressReadDTO, GovernorateValue } from "./addressTypes";

// #ARCHITECTURE-ADDRESS-ADAPTER
//
// Phase 5B — the frontend shape of the real AddressRead (addressTypes.ts).
// Every field is a 1:1 camelCase copy; nothing is derived except the
// presentation-only `displayLines`, which checkout's
// DeliveryMethodSelector also renders.
//
// #ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE — ADR-024: no shipping zones,
// no website-calculated shipping fee, no free-shipping threshold. An
// address is contact/delivery information only; the governorate is part
// of the address, never a price selector.
export interface AddressModel {
  id: string;
  label: string;
  recipientName: string;
  phone: string;
  governorate: GovernorateValue;
  city: string;
  area: string | null;
  street: string | null;
  landmarkNotes: string;
  isDefault: boolean;
  displayLines: readonly string[];
}

// Frontend-owned display names for the backend's Governorate enum, in
// the contract's own order.
export const GOVERNORATES: readonly { value: GovernorateValue; label: string }[] = [
  { value: "akkar", label: "Akkar" },
  { value: "baalbek_hermel", label: "Baalbek-Hermel" },
  { value: "beirut", label: "Beirut" },
  { value: "beqaa", label: "Beqaa" },
  { value: "keserwan_jbeil", label: "Keserwan-Jbeil" },
  { value: "mount_lebanon", label: "Mount Lebanon" },
  { value: "nabatieh", label: "Nabatieh" },
  { value: "north", label: "North" },
  { value: "south", label: "South" },
];

// An enum value added server-side later still renders readably instead
// of crashing or showing an empty string.
export function governorateLabel(value: string): string {
  const known = GOVERNORATES.find((option) => option.value === value);
  if (known) {
    return known.label;
  }
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function adaptAddress(dto: AddressReadDTO): AddressModel {
  const streetLine = [dto.street, dto.area].filter((part): part is string => Boolean(part)).join(", ");
  const displayLines = [
    dto.recipient_name,
    streetLine,
    `${dto.city}, ${governorateLabel(dto.governorate)}`,
    dto.phone,
  ].filter((line) => line !== "");

  return {
    id: dto.id,
    label: dto.label,
    recipientName: dto.recipient_name,
    phone: dto.phone,
    governorate: dto.governorate,
    city: dto.city,
    area: dto.area,
    street: dto.street,
    landmarkNotes: dto.landmark_notes,
    isDefault: dto.is_default,
    displayLines,
  };
}
