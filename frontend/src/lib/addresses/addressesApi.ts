import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { AddressCreateDTO, AddressListDTO, AddressReadDTO, AddressUpdateDTO } from "./addressTypes";

// #ARCHITECTURE-ADDRESSES-API
//
// Every built customer address operation in the current contract
// (openapi.json; backend 2dfb27b src/app/identity/api/addresses.py):
//   GET    /api/v1/me/addresses                 list (default first, capped)
//   POST   /api/v1/me/addresses                 create  -> 201 AddressRead
//   GET    /api/v1/me/addresses/{id}            read one
//   PATCH  /api/v1/me/addresses/{id}            partial edit -> AddressRead
//   DELETE /api/v1/me/addresses/{id}            soft delete -> 204
//   PUT    /api/v1/me/addresses/{id}/default    make default -> AddressRead
// Reads need a session; every write needs the double-submit CSRF header
// and a verified email (403 EMAIL_VERIFICATION_REQUIRED otherwise).
// Another user's, a deleted and an unknown id all give one 404.
// All calls share the single refresh-on-401-then-retry-once wrapper.
const BASE = "/api/v1/me/addresses";

function addressPath(addressId: string): string {
  return `${BASE}/${encodeURIComponent(addressId)}`;
}

function listAddresses(): Promise<AddressListDTO> {
  return authenticatedRequest(() => apiClient.get<AddressListDTO>(BASE));
}

function readAddress(addressId: string): Promise<AddressReadDTO> {
  return authenticatedRequest(() => apiClient.get<AddressReadDTO>(addressPath(addressId)));
}

function createAddress(body: AddressCreateDTO): Promise<AddressReadDTO> {
  return authenticatedRequest(() => apiClient.post<AddressReadDTO>(BASE, body, { csrf: true }));
}

function updateAddress(addressId: string, patch: AddressUpdateDTO): Promise<AddressReadDTO> {
  return authenticatedRequest(() => apiClient.patch<AddressReadDTO>(addressPath(addressId), patch, { csrf: true }));
}

function deleteAddress(addressId: string): Promise<void> {
  return authenticatedRequest(() => apiClient.del<void>(addressPath(addressId), { csrf: true }));
}

function setDefaultAddress(addressId: string): Promise<AddressReadDTO> {
  return authenticatedRequest(() =>
    apiClient.put<AddressReadDTO>(`${addressPath(addressId)}/default`, undefined, { csrf: true })
  );
}

export const addressesApi = {
  listAddresses,
  readAddress,
  createAddress,
  updateAddress,
  deleteAddress,
  setDefaultAddress,
};
