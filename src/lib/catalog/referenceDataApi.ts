import { apiClient } from "@/lib/api/apiClient";

// #ARCHITECTURE-REFERENCE-DATA-API
//
// Confirmed wire contract (BACKEND-RESPONSE.md B2 notes; openapi.json
// CategoryList/CategoryRead, MaterialList/MaterialRead, ColourList/
// ColourRead): three unpaginated `{items: [...]}` lists, at most 100 rows
// each. Categories carry a slug; materials/colours do not (reference-data
// skill convention, NOT this project's invention — see
// src/components/admin/referenceDataTypes.ts for the admin-side generic
// shape this intentionally mirrors in spirit but keeps separate from,
// since the public read contract and the admin CRUD contract are
// different schemas).
export interface CategoryRead {
  id: string;
  name: string;
  slug: string;
}

export interface MaterialRead {
  id: string;
  name: string;
}

export interface ColourRead {
  id: string;
  name: string;
}

async function getCategories(): Promise<readonly CategoryRead[]> {
  const page = await apiClient.get<{ items: CategoryRead[] }>("/api/v1/categories");
  return page.items;
}

async function getMaterials(): Promise<readonly MaterialRead[]> {
  const page = await apiClient.get<{ items: MaterialRead[] }>("/api/v1/materials");
  return page.items;
}

async function getColours(): Promise<readonly ColourRead[]> {
  const page = await apiClient.get<{ items: ColourRead[] }>("/api/v1/colours");
  return page.items;
}

export const referenceDataApi = { getCategories, getMaterials, getColours };

// One shared query-key family per entity, so FilterPanel (FVS-013), the
// home page's category showcase (FVS-022), and any future consumer never
// invent a second cache entry for the same GET.
export const referenceDataKeys = {
  categories: () => ["referenceData", "categories"] as const,
  materials: () => ["referenceData", "materials"] as const,
  colours: () => ["referenceData", "colours"] as const,
};
