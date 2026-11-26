import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddressForm } from "./AddressForm";
import { addressFormDefaults } from "@/lib/addresses/addressPayloads";
import { adaptAddress } from "@/lib/addresses/addressModel";

// Phase 5B — the real AddressCreate/AddressUpdate field set. Client
// validation is UX only; the server's 422 is authoritative and maps back
// onto these fields.

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/^label/i), "Home");
  await user.type(screen.getByLabelText(/recipient name/i), "Jane Doe");
  await user.type(screen.getByLabelText(/^phone/i), "03 123 456");
  await user.selectOptions(screen.getByLabelText(/governorate/i), "beirut");
  await user.type(screen.getByLabelText(/^city/i), "Beirut");
  await user.type(screen.getByLabelText(/landmark notes/i), "Blue gate");
}

function renderForm(overrides: Partial<Parameters<typeof AddressForm>[0]> = {}) {
  const props = {
    initialValues: addressFormDefaults(),
    submitLabel: "Save address",
    onSubmit: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn(),
    ...overrides,
  };
  render(<AddressForm {...props} />);
  return props;
}

describe("AddressForm", () => {
  it("renders exactly the contract's fields, with required/optional marked", () => {
    renderForm();
    for (const label of [/^label/i, /recipient name/i, /^phone/i, /governorate/i, /^city/i, /landmark notes/i]) {
      expect(screen.getByLabelText(label)).toBeRequired();
    }
    expect(screen.getByLabelText(/area \(optional\)/i)).not.toBeRequired();
    expect(screen.getByLabelText(/street \(optional\)/i)).not.toBeRequired();
    expect(screen.queryByLabelText(/postal|zip|country|zone/i)).not.toBeInTheDocument();
  });

  it("offers exactly the nine governorates plus an unselected prompt", () => {
    renderForm();
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(10);
    expect(options[0]).toHaveValue("");
    expect(screen.getByRole("option", { name: "Baalbek-Hermel" })).toHaveValue("baalbek_hermel");
  });

  it("blocks submit with field errors when required fields are empty, and focuses the first invalid field", async () => {
    const user = userEvent.setup();
    const props = renderForm();
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/^label/i)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/governorate/i)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Choose a governorate.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^label/i)).toHaveFocus();
  });

  it("rejects whitespace-only required values client-side", async () => {
    const user = userEvent.setup();
    const props = renderForm();
    await fillValid(user);
    await user.clear(screen.getByLabelText(/^city/i));
    await user.type(screen.getByLabelText(/^city/i), "   ");
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a city.")).toBeInTheDocument();
  });

  it("caps every input at the backend's own maximum length", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/^label/i), "x".repeat(60));
    expect(screen.getByLabelText(/^label/i)).toHaveValue("x".repeat(50));
    const limits: [RegExp, number][] = [
      [/recipient name/i, 100],
      [/^phone/i, 32],
      [/^city/i, 100],
      [/area \(optional\)/i, 100],
      [/street \(optional\)/i, 200],
      [/landmark notes/i, 500],
    ];
    for (const [label, max] of limits) {
      expect(screen.getByLabelText(label)).toHaveAttribute("maxLength", String(max));
    }
  });

  it("submits the raw values once valid", async () => {
    const user = userEvent.setup();
    const props = renderForm();
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(props.onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ label: "Home", governorate: "beirut", phone: "03 123 456", is_default: false })
    );
  });

  it("shows server field errors returned by onSubmit on the matching inputs and focuses the first", async () => {
    const user = userEvent.setup();
    renderForm({
      onSubmit: vi.fn().mockResolvedValue([
        { field: "phone", message: "Enter a Lebanese phone number, e.g. 03 123 456 or +961 71 123 456." },
      ]),
    });
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    const phone = screen.getByLabelText(/^phone/i);
    expect(await screen.findByText(/enter a lebanese phone number/i)).toBeInTheDocument();
    expect(phone).toHaveAttribute("aria-invalid", "true");
    expect(phone).toHaveFocus();
  });

  it("renders a form-level error as an alert", () => {
    renderForm({ formError: "Your address book is full. Delete an address before adding a new one." });
    expect(screen.getByRole("alert")).toHaveTextContent(/address book is full/i);
  });

  it("pre-fills an existing address for editing", () => {
    const address = adaptAddress({
      id: "addr-1",
      label: "Work",
      recipient_name: "John",
      phone: "+96171123456",
      governorate: "north",
      city: "Tripoli",
      area: null,
      street: "Port Road",
      landmark_notes: "Near the port",
      is_default: true,
      created_at: "2026-11-01T10:00:00Z",
      updated_at: "2026-11-01T10:00:00Z",
    });
    renderForm({ initialValues: addressFormDefaults(address) });
    expect(screen.getByLabelText(/^label/i)).toHaveValue("Work");
    expect(screen.getByLabelText(/governorate/i)).toHaveValue("north");
    expect(screen.getByLabelText(/area \(optional\)/i)).toHaveValue("");
    expect(screen.getByLabelText(/default address/i)).toBeChecked();
  });

  it("hides the default checkbox when the address will become the default automatically", () => {
    renderForm({ defaultIsAutomatic: true });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/first address becomes your default/i)).toBeInTheDocument();
  });

  it("Cancel calls onCancel without submitting", async () => {
    const user = userEvent.setup();
    const props = renderForm();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onSubmit).not.toHaveBeenCalled();
  });
});
