"use client";

import { useEffect, useId } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { TextField } from "@/components/forms/TextField";
import { SelectField } from "@/components/forms/SelectField";
import { TextAreaField } from "@/components/forms/TextAreaField";
import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { GOVERNORATES } from "@/lib/addresses/addressModel";
import { ADDRESS_FIELD_LIMITS } from "@/lib/addresses/addressTypes";
import type { AddressFormValues } from "@/lib/addresses/addressPayloads";
import type { FieldValidationError } from "@/lib/api/validationErrors";

// Client-side validation mirrors the backend's documented rules for fast
// feedback only (trimmed non-empty required text, max lengths, a
// governorate chosen, phone characters). The server stays authoritative:
// the Lebanese-number rule itself is checked there and its 422 maps back
// onto the phone field.
const PHONE_CHARACTERS = /^\+?[0-9 ().-]+$/;

function requiredText(message: string, max: number) {
  return z
    .string()
    .refine((value) => value.trim().length > 0, message)
    .refine((value) => value.trim().length <= max, `Use at most ${max} characters.`);
}

function optionalText(max: number) {
  return z.string().refine((value) => value.trim().length <= max, `Use at most ${max} characters.`);
}

const GOVERNORATE_VALUES = GOVERNORATES.map((option) => option.value) as string[];

const addressFormSchema = z.object({
  label: requiredText("Enter a label, e.g. Home or Work.", ADDRESS_FIELD_LIMITS.label),
  recipient_name: requiredText("Enter the recipient's name.", ADDRESS_FIELD_LIMITS.recipient_name),
  phone: requiredText("Enter a phone number.", ADDRESS_FIELD_LIMITS.phone).refine(
    (value) => value.trim() === "" || PHONE_CHARACTERS.test(value.trim()),
    "Use digits, spaces and an optional leading +."
  ),
  governorate: z.string().refine((value) => GOVERNORATE_VALUES.includes(value), "Choose a governorate."),
  city: requiredText("Enter a city.", ADDRESS_FIELD_LIMITS.city),
  area: optionalText(ADDRESS_FIELD_LIMITS.area),
  street: optionalText(ADDRESS_FIELD_LIMITS.street),
  landmark_notes: requiredText("Add landmark notes so the courier can find you.", ADDRESS_FIELD_LIMITS.landmark_notes),
  is_default: z.boolean(),
});

const FIELD_ORDER: readonly (keyof AddressFormValues)[] = [
  "label",
  "recipient_name",
  "phone",
  "governorate",
  "city",
  "area",
  "street",
  "landmark_notes",
  "is_default",
];

export interface AddressFormProps {
  initialValues: AddressFormValues;
  submitLabel: string;
  // Resolves with server field errors to show, or nothing on success.
  onSubmit: (values: AddressFormValues) => Promise<readonly FieldValidationError[] | void>;
  onCancel: () => void;
  formError?: string | null;
  // The backend makes a user's first live address the default regardless.
  defaultIsAutomatic?: boolean;
}

// #FVS023-ADDRESS-FORM — exactly the AddressCreate/AddressUpdate fields.
// No postal code, country, zone or price field exists in the contract.
export function AddressForm({
  initialValues,
  submitLabel,
  onSubmit,
  onCancel,
  formError,
  defaultIsAutomatic = false,
}: AddressFormProps) {
  const checkboxId = useId();
  const {
    register,
    handleSubmit,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<AddressFormValues>({
    resolver: zodResolver(addressFormSchema) as unknown as Resolver<AddressFormValues>,
    defaultValues: initialValues,
  });

  // Move focus into the dialog on open. An effect rather than autoFocus:
  // autoFocus fires during commit, before DialogShell has recorded the
  // trigger it must return focus to on close.
  useEffect(() => {
    setFocus("label");
  }, [setFocus]);

  async function submit(values: AddressFormValues) {
    const serverErrors = await onSubmit(values);
    if (!serverErrors || serverErrors.length === 0) {
      return;
    }
    for (const item of serverErrors) {
      setError(item.field as keyof AddressFormValues, { type: "server", message: item.message });
    }
    const first = FIELD_ORDER.find((field) => serverErrors.some((item) => item.field === field));
    if (first) {
      setFocus(first);
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex flex-col gap-4">
      {formError && <Alert variant="error" message={formError} />}
      <fieldset disabled={isSubmitting} className="contents">
        <div className="grid grid-cols-1 gap-4 tablet:grid-cols-2">
          <TextField
            label="Label"
            hint="A name for this address, e.g. Home or Work."
            required
            maxLength={ADDRESS_FIELD_LIMITS.label}
            error={errors.label?.message}
            {...register("label")}
          />
          <TextField
            label="Recipient name"
            required
            autoComplete="name"
            maxLength={ADDRESS_FIELD_LIMITS.recipient_name}
            error={errors.recipient_name?.message}
            {...register("recipient_name")}
          />
          <TextField
            label="Phone"
            hint="Lebanese number, e.g. 03 123 456 or +961 71 123 456."
            required
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            maxLength={ADDRESS_FIELD_LIMITS.phone}
            error={errors.phone?.message}
            {...register("phone")}
          />
          <SelectField label="Governorate" required error={errors.governorate?.message} {...register("governorate")}>
            <option value="">Select a governorate</option>
            {GOVERNORATES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectField>
          <TextField
            label="City"
            required
            autoComplete="address-level2"
            maxLength={ADDRESS_FIELD_LIMITS.city}
            error={errors.city?.message}
            {...register("city")}
          />
          <TextField
            label="Area (optional)"
            autoComplete="address-level3"
            maxLength={ADDRESS_FIELD_LIMITS.area}
            error={errors.area?.message}
            {...register("area")}
          />
          <div className="tablet:col-span-2">
            <TextField
              label="Street (optional)"
              autoComplete="address-line1"
              maxLength={ADDRESS_FIELD_LIMITS.street}
              error={errors.street?.message}
              {...register("street")}
            />
          </div>
          <div className="tablet:col-span-2">
            <TextAreaField
              label="Landmark notes"
              hint="Nearby landmarks, building, floor — how a courier finds you."
              required
              maxLength={ADDRESS_FIELD_LIMITS.landmark_notes}
              error={errors.landmark_notes?.message}
              {...register("landmark_notes")}
            />
          </div>
        </div>

        {defaultIsAutomatic ? (
          <p className="rounded-lg bg-surface-container-low p-3 text-body-md text-on-surface-variant">
            Your first address becomes your default automatically.
          </p>
        ) : (
          <div className="flex min-h-11 items-center gap-3 rounded-lg bg-surface-container-low px-3 py-2">
            <input
              id={checkboxId}
              type="checkbox"
              className="h-5 w-5 shrink-0 cursor-pointer rounded-badge accent-primary"
              {...register("is_default")}
            />
            <label htmlFor={checkboxId} className="cursor-pointer text-body-md text-on-surface">
              Use as my default address
            </label>
          </div>
        )}

        <div className="flex flex-col-reverse gap-3 border-t border-outline-variant/30 pt-6 tablet:flex-row tablet:justify-end">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isSubmitting}>
            {submitLabel}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
