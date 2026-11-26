import { useQuery } from "@tanstack/react-query";
import { useDebouncedValue } from "@/lib/shared/useDebouncedValue";
import { searchSuggestionsApi, searchSuggestionsKeys } from "./searchSuggestionsApi";

// #ARCHITECTURE-SEARCH-SUGGESTIONS-QUERY
//
// Confirmed, ~300ms debounce per B5's own note. The debounced term is
// itself part of the TanStack query key (searchSuggestionsKeys.byQuery),
// so a stale in-flight response can never overwrite a newer one: each
// keystroke-settled term gets its OWN cache entry, and the hook always
// renders the entry for the CURRENT debounced term — an older request
// that resolves late simply populates a key nothing is reading anymore,
// it never clobbers the current result. This is the one correct way to
// get "ignore stale responses" from TanStack Query's own cache semantics,
// never a manually-tracked request-sequence counter.
//
// Below the 3-character minimum (B5), the query is disabled entirely: no
// request is sent, which both avoids the guaranteed 422 and avoids
// consuming the rate limit on input the backend will reject anyway.
const SEARCH_SUGGESTIONS_DEBOUNCE_MS = 300;

export function useSearchSuggestions(query: string) {
  const debouncedQuery = useDebouncedValue(query.trim(), SEARCH_SUGGESTIONS_DEBOUNCE_MS);
  const isQueryLongEnough = debouncedQuery.length >= searchSuggestionsApi.MIN_QUERY_LENGTH;

  const result = useQuery({
    queryKey: searchSuggestionsKeys.byQuery(debouncedQuery),
    queryFn: () => searchSuggestionsApi.getSearchSuggestions(debouncedQuery),
    enabled: isQueryLongEnough,
    retry: false,
  });

  return {
    ...result,
    // Distinguishes "below minimum length, no request made" from "query
    // in flight" / "query settled with zero matches" — a caller should
    // never show a loading or empty-results state for input that was
    // never even sent.
    isQueryLongEnough,
  };
}
