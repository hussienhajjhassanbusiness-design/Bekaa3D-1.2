import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import { refreshSession } from "@/lib/auth/refreshSession";
import { addressesApi } from "./addressesApi";
import type { AddressCreateDTO, AddressReadDTO } from "./addressTypes";

// The six built customer address operations (openapi.json, backend
// 2dfb27b src/app/identity/api/addresses.py): reads need a session,
// every write needs CSRF + a verified email.

vi.mock("@/lib/auth/refreshSession", () => ({ refreshSession: vi.fn() }));
const mockedRefreshSession = vi.mocked(refreshSession);

afterEach(() => {
  vi.restoreAllMocks();
});

const DTO: AddressReadDTO = {
  id: "addr-1",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: null,
  street: null,
  landmark_notes: "Blue gate",
  is_default: true,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const CREATE: AddressCreateDTO = {
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "03 123 456",
  governorate: "beirut",
  city: "Beirut",
  area: null,
  street: null,
  landmark_notes: "Blue gate",
  is_default: false,
};

const AUTH_REQUIRED = { kind: "http" as const, status: 401, code: "AUTH_REQUIRED", message: "x", raw: {} };

describe("addressesApi", () => {
  it("listAddresses: GET /api/v1/me/addresses (no CSRF, no query params — the list is hard-capped, not paginated)", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [DTO] });
    await expect(addressesApi.listAddresses()).resolves.toEqual({ items: [DTO] });
    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/addresses");
  });

  it("readAddress: GET /api/v1/me/addresses/{id}, id URL-encoded", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue(DTO);
    await addressesApi.readAddress("a/b");
    expect(getSpy).toHaveBeenCalledWith("/api/v1/me/addresses/a%2Fb");
  });

  it("createAddress: POST /api/v1/me/addresses with the body and csrf: true", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(DTO);
    await addressesApi.createAddress(CREATE);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/me/addresses", CREATE, { csrf: true });
  });

  it("updateAddress: PATCH /api/v1/me/addresses/{id} with exactly the patch and csrf: true", async () => {
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue(DTO);
    await addressesApi.updateAddress("addr-1", { city: "Tripoli", area: null });
    expect(patchSpy).toHaveBeenCalledWith("/api/v1/me/addresses/addr-1", { city: "Tripoli", area: null }, { csrf: true });
  });

  it("deleteAddress: DELETE /api/v1/me/addresses/{id} with csrf: true", async () => {
    const delSpy = vi.spyOn(apiClient, "del").mockResolvedValue(undefined);
    await addressesApi.deleteAddress("addr-1");
    expect(delSpy).toHaveBeenCalledWith("/api/v1/me/addresses/addr-1", { csrf: true });
  });

  it("setDefaultAddress: PUT /api/v1/me/addresses/{id}/default, no body, csrf: true", async () => {
    const putSpy = vi.spyOn(apiClient, "put").mockResolvedValue(DTO);
    await addressesApi.setDefaultAddress("addr-1");
    expect(putSpy).toHaveBeenCalledWith("/api/v1/me/addresses/addr-1/default", undefined, { csrf: true });
  });

  it("every call goes through authenticatedRequest — one refresh on 401 AUTH_REQUIRED, then one retry", async () => {
    mockedRefreshSession.mockResolvedValue(true);
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValueOnce(AUTH_REQUIRED).mockResolvedValueOnce(DTO);
    await expect(addressesApi.createAddress(CREATE)).resolves.toEqual(DTO);
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(mockedRefreshSession).toHaveBeenCalledTimes(1);
  });
});
