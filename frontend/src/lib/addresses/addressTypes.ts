// Phase 5B — FVS-023 wire types, transcribed from the current contract:
// docs/backend-handoff/openapi.json (components.schemas.AddressRead /
// AddressList / AddressCreate / AddressUpdate / Governorate), checked
// equal to the running backend 2dfb27b /openapi.json and to the backend
// repo's own docs/frontend-handoff/openapi.json. Field names, required-
// ness and nullability are exact; do not add a field the contract lacks.

// Lebanon's nine governorates (VS-026 Q2, BR-071: Lebanese addresses only).
export type GovernorateValue =
  | "akkar"
  | "baalbek_hermel"
  | "beirut"
  | "beqaa"
  | "keserwan_jbeil"
  | "mount_lebanon"
  | "nabatieh"
  | "north"
  | "south";

export interface AddressReadDTO {
  id: string;
  label: string;
  recipient_name: string;
  // Returned as E.164 (+961…), normalised by the backend.
  phone: string;
  governorate: GovernorateValue;
  city: string;
  area: string | null;
  street: string | null;
  landmark_notes: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

// Every live address, default first; hard-capped (not paginated).
export interface AddressListDTO {
  items: AddressReadDTO[];
}

// additionalProperties: false. Server limits: label 50, recipient_name
// 100, phone 32 (Lebanese, any common format), city 100, area 100,
// street 200, landmark_notes 500. The first live address becomes the
// default regardless of is_default.
export interface AddressCreateDTO {
  label: string;
  recipient_name: string;
  phone: string;
  governorate: GovernorateValue;
  city: string;
  area?: string | null;
  street?: string | null;
  landmark_notes: string;
  is_default?: boolean;
}

// additionalProperties: false; at least one key. Omitted = unchanged.
// `null` clears area/street only — null on a required field is refused
// (422), so the frontend never sends it. is_default: true sets the
// default, false clears it (leaving no default).
export interface AddressUpdateDTO {
  label?: string;
  recipient_name?: string;
  phone?: string;
  governorate?: GovernorateValue;
  city?: string;
  area?: string | null;
  street?: string | null;
  landmark_notes?: string;
  is_default?: boolean;
}

export const ADDRESS_FIELD_LIMITS = {
  label: 50,
  recipient_name: 100,
  phone: 32,
  city: 100,
  area: 100,
  street: 200,
  landmark_notes: 500,
} as const;
