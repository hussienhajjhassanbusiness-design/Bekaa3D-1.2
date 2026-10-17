import { apiClient } from "@/lib/api/apiClient";
import { adminRequest } from "@/lib/admin/adminRequest";
import type { AdminProductsQueryParams, RawAdminProductDetail, RawAdminProductPage } from "./productAdminTypes";

function buildListSearchParams(params: AdminProductsQueryParams): URLSearchParams {
  const search = new URLSearchParams();
  if (params.type) search.set("type", params.type);
  if (params.category_id) search.set("category_id", params.category_id);
  if (params.is_visible !== undefined) search.set("is_visible", String(params.is_visible));
  if (params.is_featured !== undefined) search.set("is_featured", String(params.is_featured));
  if (params.is_available !== undefined) search.set("is_available", String(params.is_available));
  if (params.deleted !== undefined) search.set("deleted", String(params.deleted));
  if (params.q) search.set("q", params.q);
  if (params.sort) search.set("sort", params.sort);
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  return search;
}

async function listProducts(params: AdminProductsQueryParams): Promise<RawAdminProductPage> {
  const search = buildListSearchParams(params).toString();
  const path = search ? `/api/v1/admin/products?${search}` : "/api/v1/admin/products";
  return adminRequest(() => apiClient.get<RawAdminProductPage>(path));
}

async function getProduct(productId: string): Promise<RawAdminProductDetail> {
  return adminRequest(() => apiClient.get<RawAdminProductDetail>(`/api/v1/admin/products/${encodeURIComponent(productId)}`));
}

async function createProduct(body: Record<string, unknown>): Promise<RawAdminProductDetail> {
  return adminRequest(() => apiClient.post<RawAdminProductDetail>("/api/v1/admin/products", body, { csrf: true }));
}

async function updateProduct(productId: string, body: Record<string, unknown>): Promise<RawAdminProductDetail> {
  return adminRequest(() =>
    apiClient.patch<RawAdminProductDetail>(`/api/v1/admin/products/${encodeURIComponent(productId)}`, body, { csrf: true })
  );
}

// Version travels in the query string on DELETE, never the body (P1-6).
async function deleteProduct(productId: string, version: number): Promise<void> {
  await adminRequest(() =>
    apiClient.del(`/api/v1/admin/products/${encodeURIComponent(productId)}`, { csrf: true, query: { version } })
  );
}

export const productsAdminApi = { listProducts, getProduct, createProduct, updateProduct, deleteProduct };

export const productsAdminKeys = {
  root: ["admin", "products"] as const,
  list: (params: AdminProductsQueryParams) => [...productsAdminKeys.root, "list", params] as const,
  detail: (productId: string) => [...productsAdminKeys.root, "detail", productId] as const,
};
