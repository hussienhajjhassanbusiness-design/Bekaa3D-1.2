import { describe, it, expect } from "vitest";
import {
  addressFormDefaults,
  buildAddressCreatePayload,
  buildAddressUpdatePayload,
  type AddressFormValues,
} from "./addressPayloads";
import { adaptAddress } from "./addressModel";
import type { AddressReadDTO } from "./addressTypes";

// AddressCreate (additionalProperties: false): required label,
// recipient_name, phone, governorate, city, landmark_notes; optional
// area|null, street|null, is_default (default false).
// AddressUpdate (additionalProperties: false): any subset; an OMITTED
// field is left unchanged; `null` clears area/street; `null` on a
// required field is a 422 (backend AddressDetails re-validates), so it
// is never sent; is_default true/false sets/clears, omitted leaves it.

const VALUES: AddressFormValues = {
  label: "  Home ",
  recipient_name: "Jane Doe",
  phone: "03 123 456",
  governorate: "beirut",
  city: "Beirut",
  area: "",
  street: "  ",
  landmark_notes: "Blue gate\nsecond floor",
  is_default: false,
};

const EXISTING: AddressReadDTO = {
  id: "addr-1",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: "Hamra",
  street: "Bliss Street",
  landmark_notes: "Blue gate",
  is_default: false,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

describe("buildAddressCreatePayload", () => {
  it("sends exactly the AddressCreate keys, trimmed, with blank optionals as null", () => {
    expect(buildAddressCreatePayload(VALUES)).toEqual({
      label: "Home",
      recipient_name: "Jane Doe",
      phone: "03 123 456",
      governorate: "beirut",
      city: "Beirut",
      area: null,
      street: null,
      landmark_notes: "Blue gate\nsecond floor",
      is_default: false,
    });
  });

  it("keeps a filled area/street and passes is_default through", () => {
    const payload = buildAddressCreatePayload({ ...VALUES, area: " Hamra ", street: "Bliss", is_default: true });
    expect(payload.area).toBe("Hamra");
    expect(payload.street).toBe("Bliss");
    expect(payload.is_default).toBe(true);
  });

  it("never sends a key outside the contract (extra fields are forbidden by the backend)", () => {
    expect(Object.keys(buildAddressCreatePayload(VALUES)).sort()).toEqual(
      ["area", "city", "governorate", "is_default", "label", "landmark_notes", "phone", "recipient_name", "street"].sort()
    );
  });
});

describe("addressFormDefaults", () => {
  it("is blank for a new address (governorate unselected)", () => {
    expect(addressFormDefaults()).toEqual({
      label: "",
      recipient_name: "",
      phone: "",
      governorate: "",
      city: "",
      area: "",
      street: "",
      landmark_notes: "",
      is_default: false,
    });
  });

  it("pre-fills from an existing address, null optionals as empty inputs", () => {
    const defaults = addressFormDefaults(adaptAddress({ ...EXISTING, street: null }));
    expect(defaults).toEqual({
      label: "Home",
      recipient_name: "Jane Doe",
      phone: "+9613123456",
      governorate: "beirut",
      city: "Beirut",
      area: "Hamra",
      street: "",
      landmark_notes: "Blue gate",
      is_default: false,
    });
  });
});

describe("buildAddressUpdatePayload", () => {
  const original = adaptAddress(EXISTING);
  const unchanged = addressFormDefaults(original);

  it("returns an empty patch when nothing changed (the caller then sends no request)", () => {
    expect(buildAddressUpdatePayload(original, unchanged)).toEqual({});
  });

  it("omits unchanged fields and sends only the changed ones, trimmed", () => {
    expect(buildAddressUpdatePayload(original, { ...unchanged, city: " Beirut Central ", label: "Home" })).toEqual({
      city: "Beirut Central",
    });
  });

  it("treats whitespace-only differences as unchanged", () => {
    expect(buildAddressUpdatePayload(original, { ...unchanged, label: "  Home  " })).toEqual({});
  });

  it("sends null to clear a previously-set area or street", () => {
    expect(buildAddressUpdatePayload(original, { ...unchanged, area: "", street: "   " })).toEqual({
      area: null,
      street: null,
    });
  });

  it("does not send null for an optional field that was already empty", () => {
    const noArea = adaptAddress({ ...EXISTING, area: null });
    expect(buildAddressUpdatePayload(noArea, { ...addressFormDefaults(noArea), area: "" })).toEqual({});
  });

  it("sends is_default only when it changed, as an explicit boolean", () => {
    expect(buildAddressUpdatePayload(original, { ...unchanged, is_default: true })).toEqual({ is_default: true });
    const def = adaptAddress({ ...EXISTING, is_default: true });
    expect(buildAddressUpdatePayload(def, { ...addressFormDefaults(def), is_default: false })).toEqual({
      is_default: false,
    });
  });

  it("sends governorate and phone changes verbatim (the server normalises the phone)", () => {
    expect(
      buildAddressUpdatePayload(original, { ...unchanged, governorate: "north", phone: "71 123 456" })
    ).toEqual({ governorate: "north", phone: "71 123 456" });
  });
});
