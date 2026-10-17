import type { ReactNode } from "react";

// #ARCHITECTURE-REFERENCE-DATA-ADAPTER
//
// Frontend-normalized UI shape shared by the three near-identical
// reference-data entities (categories/materials/colours) — NOT a claim
// about any backend field name. The real Category/Material/Colour
// request/response shapes are still NEEDS BACKEND CONFIRMATION
// (FVS-010-IMPLEMENTATION-PLAN.md §1). A future per-entity API adapter
// maps whatever the backend actually returns onto this shape in one
// place; ReferenceDataManager and its tests never see a backend field
// name directly.
//
// `swatchValue` is a generic, optional supplemental display value (e.g. a
// colour's hex-like value) — its presence is a UI config decision
// (config.hasSwatchField), never a claimed backend "hex" field name.
export interface ReferenceDataEntry {
  id: string;
  name: string;
  isArchived: boolean;
  // Reversible enable/disable (AGENTS.md: "PATCH is used for reversible
  // enable/disable", distinct from the permanent DELETE/archive). Optional
  // so a caller that doesn't track this concept (or an older fixture)
  // still satisfies the type — undefined is treated as "live" (active).
  isActive?: boolean;
  swatchValue?: string;
}

export interface ReferenceDataDraft {
  name: string;
  swatchValue?: string;
}

export type ReferenceDataFieldErrors = Partial<Record<"name" | "swatchValue", string>>;

// Configuration owns every per-entity difference — ReferenceDataManager
// itself must never branch on "is this categories/materials/colours".
// Only what the presentational layer actually needs exists here — no
// generic schema framework, no speculative metadata.
export interface ReferenceDataEntityConfig {
  entityLabelSingular: string;
  entityLabelPlural: string;
  emptyStateMessage: string;
  hasSwatchField?: boolean;
  swatchFieldLabel?: string;
  renderSwatch?: (value: string) => ReactNode;
}
