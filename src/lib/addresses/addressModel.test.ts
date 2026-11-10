import { describe, it, expect } from "vitest";
import { adaptAddress, governorateLabel, GOVERNORATES } from "./addressModel";
import type { AddressReadDTO } from "./addressTypes";

// Phase 5B — FVS-023 against the real contract. AddressRead
// (docs/backend-handoff/openapi.json, components.schemas.AddressRead,
// identical to the running backend 2dfb27b): id, label, recipient_name,
// phone (E.164), governorate (enum), city, area|null, street|null,
// landmark_notes, is_default, created_at, updated_at — all required.

const DTO: AddressReadDTO = {
  id: "0b6f0f8e-1d7c-4f55-9b1e-2f1d8c5a9a01",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "mount_lebanon",
  city: "Jounieh",
  area: "Kaslik",
  street: "Main Street",
  landmark_notes: "Blue gate next to the bakery",
  is_default: true,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-02T10:00:00Z",
};

describe("adaptAddress", () => {
  it("maps every AddressRead field to the camelCase model, unchanged", () => {
    const model = adaptAddress(DTO);
    expect(model).toMatchObject({
      id: DTO.id,
      label: "Home",
      recipientName: "Jane Doe",
      phone: "+9613123456",
      governorate: "mount_lebanon",
      city: "Jounieh",
      area: "Kaslik",
      street: "Main Street",
      landmarkNotes: "Blue gate next to the bakery",
      isDefault: true,
    });
  });

  it("keeps a null area/street as null — never an empty string or a guess", () => {
    const model = adaptAddress({ ...DTO, area: null, street: null });
    expect(model.area).toBeNull();
    expect(model.street).toBeNull();
  });

  it("builds display lines from recipient, street/area, city + governorate and phone — skipping null parts", () => {
    expect(adaptAddress(DTO).displayLines).toEqual([
      "Jane Doe",
      "Main Street, Kaslik",
      "Jounieh, Mount Lebanon",
      "+9613123456",
    ]);
    expect(adaptAddress({ ...DTO, area: null, street: null }).displayLines).toEqual([
      "Jane Doe",
      "Jounieh, Mount Lebanon",
      "+9613123456",
    ]);
  });

  it("carries no shipping-zone, rate or fee field (ADR-024)", () => {
    const model = adaptAddress(DTO) as unknown as Record<string, unknown>;
    for (const key of ["shippingZone", "zoneId", "rateCents", "shippingFee", "freeShippingThreshold"]) {
      expect(key in model).toBe(false);
    }
  });
});

describe("governorates", () => {
  it("lists exactly the nine backend Governorate enum values, in the contract's order", () => {
    expect(GOVERNORATES.map((option) => option.value)).toEqual([
      "akkar",
      "baalbek_hermel",
      "beirut",
      "beqaa",
      "keserwan_jbeil",
      "mount_lebanon",
      "nabatieh",
      "north",
      "south",
    ]);
  });

  it("gives every enum value a frontend-owned label", () => {
    expect(governorateLabel("baalbek_hermel")).toBe("Baalbek-Hermel");
    expect(governorateLabel("keserwan_jbeil")).toBe("Keserwan-Jbeil");
    expect(governorateLabel("north")).toBe("North");
  });

  it("falls back to a readable label for an enum value this build doesn't know yet", () => {
    expect(governorateLabel("new_region")).toBe("New region");
  });
});
