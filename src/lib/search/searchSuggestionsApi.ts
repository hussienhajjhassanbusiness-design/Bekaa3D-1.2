import { apiClient } from "@/lib/api/apiClient";
import type { ProductType } from "@/lib/catalog/productTypes";

// #ARCHITECTURE-SEARCH-SUGGESTIONS-API
//
// Confirmed wire contract (BACKEND-RESPONSE.md B5; openapi.json
// SearchSuggestionRead/SearchSuggestionList): `q` is required, 3-200
// trimmed characters containing a 3+ letter/digit word (shorter is a 422
// AND still consumes the rate limit — B5's own note), `limit` is 1-10,
// default 10.
export interface SearchSuggestionRead {
  id: string;
  name: string;
  slug: string;
  type: ProductType;
}

const MIN_QUERY_LENGTH = 3;

async function getSearchSuggestions(query: string, limit?: number): Promise<readonly SearchSuggestionRead[]> {
  const search = new URLSearchParams({ q: query });
  if (limit !== undefined) {
    search.set("limit", String(limit));
  }
  const page = await apiClient.get<{ items: SearchSuggestionRead[] }>(
    `/api/v1/search/suggestions?${search.toString()}`
  );
  return page.items;
}

export const searchSuggestionsApi = { getSearchSuggestions, MIN_QUERY_LENGTH };

export const searchSuggestionsKeys = {
  root: ["searchSuggestions"] as const,
  byQuery: (query: string) => [...searchSuggestionsKeys.root, query] as const,
};
