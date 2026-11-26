import type { AddressModel } from "./addressModel";
import type { AddressCreateDTO, AddressUpdateDTO, GovernorateValue } from "./addressTypes";

// The address form's raw values. Field names are the contract's own
// (snake_case), so a 422's loc ["body", "<field>"] maps onto an input
// without a translation table. `governorate` is "" until chosen.
export interface AddressFormValues {
  label: string;
  recipient_name: string;
  phone: string;
  governorate: GovernorateValue | "";
  city: string;
  area: string;
  street: string;
  landmark_notes: string;
  is_default: boolean;
}

const REQUIRED_TEXT_FIELDS = ["label", "recipient_name", "phone", "city", "landmark_notes"] as const;
const OPTIONAL_TEXT_FIELDS = ["area", "street"] as const;

// The backend trims and turns blank optionals into null; doing the same
// here keeps the request honest and makes "changed?" comparisons exact.
function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function addressFormDefaults(address?: AddressModel): AddressFormValues {
  if (!address) {
    return {
      label: "",
      recipient_name: "",
      phone: "",
      governorate: "",
      city: "",
      area: "",
      street: "",
      landmark_notes: "",
      is_default: false,
    };
  }
  return {
    label: address.label,
    recipient_name: address.recipientName,
    phone: address.phone,
    governorate: address.governorate,
    city: address.city,
    area: address.area ?? "",
    street: address.street ?? "",
    landmark_notes: address.landmarkNotes,
    is_default: address.isDefault,
  };
}

// Form validation guarantees a governorate was chosen before this runs.
export function buildAddressCreatePayload(values: AddressFormValues): AddressCreateDTO {
  return {
    label: values.label.trim(),
    recipient_name: values.recipient_name.trim(),
    phone: values.phone.trim(),
    governorate: values.governorate as GovernorateValue,
    city: values.city.trim(),
    area: optional(values.area),
    street: optional(values.street),
    landmark_notes: values.landmark_notes.trim(),
    is_default: values.is_default,
  };
}

// Omitted-vs-null, exactly: an unchanged field is omitted; a cleared
// area/street is sent as null; a required field is only ever sent as a
// non-empty string. An empty result means "nothing to save" — the caller
// sends no PATCH (the backend refuses an empty body with a 422).
export function buildAddressUpdatePayload(original: AddressModel, values: AddressFormValues): AddressUpdateDTO {
  const before = addressFormDefaults(original);
  const patch: AddressUpdateDTO = {};

  for (const field of REQUIRED_TEXT_FIELDS) {
    const next = values[field].trim();
    if (next !== before[field].trim()) {
      patch[field] = next;
    }
  }
  for (const field of OPTIONAL_TEXT_FIELDS) {
    const next = optional(values[field]);
    if (next !== optional(before[field])) {
      patch[field] = next;
    }
  }
  if (values.governorate !== before.governorate && values.governorate !== "") {
    patch.governorate = values.governorate;
  }
  if (values.is_default !== before.is_default) {
    patch.is_default = values.is_default;
  }
  return patch;
}
