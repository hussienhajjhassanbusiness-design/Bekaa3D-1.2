// P1-5 (docs/backend-handoff/BACKEND-RESPONSE.md) — identical CRUD shape
// across the three resources. `slug` only exists on categories; materials
// and colours have no slug field at all.
export type ReferenceDataResource = "categories" | "materials" | "colours";

export interface RawReferenceDetail {
  id: string;
  name: string;
  slug?: string;
  is_active: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RawReferencePage {
  items: RawReferenceDetail[];
  next_cursor: string | null;
}

export interface ReferenceDataCreateInput {
  name: string;
  // Categories only — the API rejects this field on materials/colours
  // (additionalProperties: false), so the admin API layer only sends it
  // for the categories resource.
  slug?: string;
  isActive?: boolean;
}

export interface ReferenceDataUpdateInput {
  name?: string;
  slug?: string;
  isActive?: boolean;
}
