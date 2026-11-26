import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { addressesApi } from "./addressesApi";
import { addressKeys } from "./addressKeys";
import {
  useAddresses,
  useCreateAddress,
  useDeleteAddress,
  useSetDefaultAddress,
  useUpdateAddress,
} from "./useAddresses";
import type { AddressCreateDTO, AddressReadDTO } from "./addressTypes";

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, invalidateSpy, wrapper };
}

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

const NOT_FOUND = { kind: "http" as const, status: 404, code: "NOT_FOUND", message: "x", raw: {} };
const CSRF_INVALID = { kind: "http" as const, status: 403, code: "CSRF_INVALID", message: "x", raw: {} };

describe("useAddresses", () => {
  it("lists through addressKeys.list() and adapts every item, keeping the server's order", async () => {
    const second = { ...DTO, id: "addr-2", label: "Work", is_default: false };
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [DTO, second] });
    const { wrapper, queryClient } = setup();
    const { result } = renderHook(() => useAddresses(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((address) => address.id)).toEqual(["addr-1", "addr-2"]);
    expect(result.current.data?.[0]?.recipientName).toBe("Jane Doe");
    expect(queryClient.getQueryData(addressKeys.list())).toBeDefined();
  });
});

describe("address mutations", () => {
  it("create calls the API with the payload and invalidates the whole address family", async () => {
    const createSpy = vi.spyOn(addressesApi, "createAddress").mockResolvedValue(DTO);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useCreateAddress(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(CREATE);
    });

    expect(createSpy).toHaveBeenCalledWith(CREATE);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: addressKeys.root });
  });

  it("update calls the API with the id and the exact patch, then invalidates", async () => {
    const updateSpy = vi.spyOn(addressesApi, "updateAddress").mockResolvedValue(DTO);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useUpdateAddress(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ id: "addr-1", patch: { street: null } });
    });

    expect(updateSpy).toHaveBeenCalledWith("addr-1", { street: null });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: addressKeys.root });
  });

  it("delete calls the API with the id, then invalidates (a deleted default leaves no default — refetch shows it)", async () => {
    const deleteSpy = vi.spyOn(addressesApi, "deleteAddress").mockResolvedValue(undefined);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useDeleteAddress(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("addr-1");
    });

    expect(deleteSpy).toHaveBeenCalledWith("addr-1");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: addressKeys.root });
  });

  it("set-default calls PUT …/default for the id, then invalidates (the previous default changed too)", async () => {
    const setSpy = vi.spyOn(addressesApi, "setDefaultAddress").mockResolvedValue(DTO);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useSetDefaultAddress(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("addr-1");
    });

    expect(setSpy).toHaveBeenCalledWith("addr-1");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: addressKeys.root });
  });

  it("a 404 from a write still refetches (the address is gone server-side), and the error propagates", async () => {
    vi.spyOn(addressesApi, "deleteAddress").mockRejectedValue(NOT_FOUND);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useDeleteAddress(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync("addr-1")).rejects.toMatchObject({ status: 404 });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: addressKeys.root });
  });

  it("any other failure propagates unchanged without a refetch, and is never retried", async () => {
    const updateSpy = vi.spyOn(addressesApi, "updateAddress").mockRejectedValue(CSRF_INVALID);
    const { wrapper, invalidateSpy } = setup();
    const { result } = renderHook(() => useUpdateAddress(), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync({ id: "addr-1", patch: { city: "X" } })).rejects.toMatchObject({
        code: "CSRF_INVALID",
      });
    });
    expect(updateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
