import { useQuery } from "@tanstack/react-query";
import { referenceDataApi, referenceDataKeys } from "./referenceDataApi";

// Reference data (categories/materials/colours) changes only through an
// admin action (FVS-010), essentially never during a storefront session —
// a 5-minute staleTime avoids refetching on every FilterPanel mount while
// still recovering within one admin working session if a row changes.
const REFERENCE_DATA_STALE_TIME_MS = 5 * 60 * 1000;

export function useCategories() {
  return useQuery({
    queryKey: referenceDataKeys.categories(),
    queryFn: referenceDataApi.getCategories,
    staleTime: REFERENCE_DATA_STALE_TIME_MS,
  });
}

export function useMaterials() {
  return useQuery({
    queryKey: referenceDataKeys.materials(),
    queryFn: referenceDataApi.getMaterials,
    staleTime: REFERENCE_DATA_STALE_TIME_MS,
  });
}

export function useColours() {
  return useQuery({
    queryKey: referenceDataKeys.colours(),
    queryFn: referenceDataApi.getColours,
    staleTime: REFERENCE_DATA_STALE_TIME_MS,
  });
}
