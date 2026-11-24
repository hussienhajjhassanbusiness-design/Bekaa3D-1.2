import { apiClient } from "@/lib/api/apiClient";
import type { ProductDetail, ProductPage, ProductsQueryParams } from "./productTypes";

// #ARCHITECTURE-PRODUCTS-QUERY-ADAPTER
//
// Confirmed wire contract (BACKEND-RESPONSE.md B2, openapi.json
// paths./api/v1/products.get): every key below is a direct quote of a real
// query parameter name. This is the ONE place that turns a
// ProductsQueryParams object into the real querystring — no other module
// builds a /api/v1/products request by hand.
//
// A parameter is included only when actually set (undefined/empty-string
// omitted) — the backend treats a present-but-blank `q` as "no search"
// (B2), and every other parameter is simply optional, so omitting an unset
// one is the correct behavior, not just a tidiness choice.
export function buildProductsSearchParams(params: ProductsQueryParams): URLSearchParams {
  const search = new URLSearchParams();

  if (params.type) search.set("type", params.type);
  if (params.category_id) search.set("category_id", params.category_id);
  if (params.material_id) search.set("material_id", params.material_id);
  if (params.colour_id) search.set("colour_id", params.colour_id);
  if (params.price_min_cents !== undefined) search.set("price_min_cents", String(params.price_min_cents));
  if (params.price_max_cents !== undefined) search.set("price_max_cents", String(params.price_max_cents));
  if (params.min_rating !== undefined) search.set("min_rating", String(params.min_rating));
  if (params.featured !== undefined) search.set("featured", String(params.featured));
  if (params.q) search.set("q", params.q);
  if (params.promotion_id) search.set("promotion_id", params.promotion_id);
  if (params.sort) search.set("sort", params.sort);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));

  return search;
}

async function listProducts(params: ProductsQueryParams): Promise<ProductPage> {
  const search = buildProductsSearchParams(params).toString();
  const path = search ? `/api/v1/products?${search}` : "/api/v1/products";
  return apiClient.get<ProductPage>(path);
}

async function getProductBySlug(slug: string): Promise<ProductDetail> {
  return apiClient.get<ProductDetail>(`/api/v1/products/${encodeURIComponent(slug)}`);
}

export const productsApi = { listProducts, getProductBySlug };

// One canonical query-key family for the catalogue, shared by /shop's
// infinite list and the home page's featured-products subset — keyed on
// the full, normalized param set (object identity doesn't matter to
// TanStack's own key-hashing) so two different filter/sort/search
// combinations are never confused for the same cached page.
export const productsKeys = {
  root: ["products"] as const,
  list: (params: ProductsQueryParams) => [...productsKeys.root, "list", params] as const,
  detail: (slug: string) => [...productsKeys.root, "detail", slug] as const,
};
