import type { ShopUrlState } from "./shopUrlState";
import type { ProductSort, ProductsQueryParams } from "./productTypes";

// #ARCHITECTURE-SHOP-QUERY-ADAPTER
//
// The ONE place that turns /shop's browser URL state (shopUrlState.ts —
// generic, cardinality-neutral `category`/`material`/`colour` string
// arrays) into the real, confirmed `GET /api/v1/products` query parameters
// (B2: `category_id`/`material_id`/`colour_id`, each a UUID, one value per
// facet — openapi.json's own parameter list). The URL stores each
// facet's selected value as that facet's real id directly (categories/
// materials/colours all expose only `id`+`name` publicly — materials and
// colours have no slug per CategoryRead/MaterialRead/ColourRead, so using
// the id for all three keeps one consistent encoding rather than slug for
// category and id for the other two).
//
// shopUrlState's own `buildShopUrlParams` already refuses to write more
// than one value per facet into the URL, so `state.category[0]` here is
// simply "the one value, if any" — never a silent truncation of a
// multi-value selection the UI never allows to exist in the first place.
const PRODUCT_SORTS: readonly ProductSort[] = ["price", "-price", "-average_rating", "-created_at", "-relevance"];

function isProductSort(value: string): value is ProductSort {
  return (PRODUCT_SORTS as readonly string[]).includes(value);
}

export function toProductsQueryParams(state: ShopUrlState): ProductsQueryParams {
  const params: ProductsQueryParams = {};

  if (state.category[0]) params.category_id = state.category[0];
  if (state.material[0]) params.material_id = state.material[0];
  if (state.colour[0]) params.colour_id = state.colour[0];
  if (state.q) params.q = state.q;
  if (state.sort && isProductSort(state.sort)) params.sort = state.sort;
  if (state.cursor) params.cursor = state.cursor;

  return params;
}
