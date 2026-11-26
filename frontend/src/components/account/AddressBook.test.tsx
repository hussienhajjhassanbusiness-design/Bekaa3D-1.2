import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AddressBook } from "./AddressBook";
import { addressesApi } from "@/lib/addresses/addressesApi";
import type { AddressReadDTO } from "@/lib/addresses/addressTypes";
import { useAuth } from "@/lib/auth/AuthProvider";

// Phase 5B — the mounted address book, end to end above the transport:
// a real QueryClient and the real hooks, with only addressesApi stubbed,
// so invalidate -> refetch is exercised for real.

vi.mock("@/lib/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

function authAs(emailVerified: boolean) {
  mockedUseAuth.mockReturnValue({
    user: {
      id: "u-1",
      email: "ada@example.com",
      role: "customer",
      emailVerified,
      emailVerifiedAt: null,
      createdAt: "2026-01-01T00:00:00Z",
    },
    isAuthenticated: true,
  } as never);
}

const HOME: AddressReadDTO = {
  id: "addr-1",
  label: "Home",
  recipient_name: "Jane Doe",
  phone: "+9613123456",
  governorate: "beirut",
  city: "Beirut",
  area: "Hamra",
  street: "Bliss Street",
  landmark_notes: "Blue gate",
  is_default: true,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};
const WORK: AddressReadDTO = { ...HOME, id: "addr-2", label: "Work", is_default: false };

function renderBook() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  render(<AddressBook />, { wrapper });
  return queryClient;
}

const http = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  kind: "http" as const,
  status,
  code,
  title: "RAW TITLE",
  detail: "RAW DETAIL",
  message: "x",
  raw: {},
  ...extra,
});

beforeEach(() => {
  authAs(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function fillNewAddress(user: ReturnType<typeof userEvent.setup>) {
  const dialog = screen.getByRole("dialog");
  await user.type(within(dialog).getByLabelText(/^label/i), "Office");
  await user.type(within(dialog).getByLabelText(/recipient name/i), "Jane Doe");
  await user.type(within(dialog).getByLabelText(/^phone/i), "71 123 456");
  await user.selectOptions(within(dialog).getByLabelText(/governorate/i), "north");
  await user.type(within(dialog).getByLabelText(/^city/i), "Tripoli");
  await user.type(within(dialog).getByLabelText(/landmark notes/i), "Above the pharmacy");
}

describe("AddressBook", () => {
  it("shows a loading state, then the server's addresses", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME, WORK] });
    renderBook();
    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Work" })).toBeInTheDocument();
  });

  it("shows the empty state, and the first address is created as the default automatically", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockResolvedValueOnce({ items: [] });
    list.mockResolvedValue({ items: [HOME] });
    const create = vi.spyOn(addressesApi, "createAddress").mockResolvedValue(HOME);
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: /add an address/i }));
    expect(within(screen.getByRole("dialog")).queryByRole("checkbox")).not.toBeInTheDocument();
    await fillNewAddress(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(create).toHaveBeenCalledWith({
      label: "Office",
      recipient_name: "Jane Doe",
      phone: "71 123 456",
      governorate: "north",
      city: "Tripoli",
      area: null,
      street: null,
      landmark_notes: "Above the pharmacy",
      is_default: false,
    });
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Address saved.")).toBeInTheDocument();
  });

  it("shows a retryable error state when the list fails, never the raw problem text", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockRejectedValueOnce(http(500, "INTERNAL_ERROR"));
    list.mockResolvedValue({ items: [HOME] });
    const user = userEvent.setup();
    renderBook();

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load your addresses/i);
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });

  it("maps a 422 VALIDATION_ERROR onto the form fields and keeps the dialog open", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME] });
    vi.spyOn(addressesApi, "createAddress").mockRejectedValue(
      http(422, "VALIDATION_ERROR", { errors: [{ loc: ["body", "phone"], msg: "invalid value", type: "value_error" }] })
    );
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Add address" }));
    await fillNewAddress(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText(/enter a lebanese phone number/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^phone/i)).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/check the highlighted fields/i);
    expect(screen.queryByText(/invalid value|RAW/)).not.toBeInTheDocument();
  });

  it("shows the limit copy on 422 ADDRESS_LIMIT_REACHED", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME] });
    vi.spyOn(addressesApi, "createAddress").mockRejectedValue(http(422, "ADDRESS_LIMIT_REACHED"));
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Add address" }));
    await fillNewAddress(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent(/address book is full/i);
  });

  it("edits with a PATCH of only the changed fields, then refetches", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockResolvedValueOnce({ items: [HOME, WORK] });
    list.mockResolvedValue({ items: [{ ...HOME, city: "Achrafieh", area: null }, WORK] });
    const update = vi.spyOn(addressesApi, "updateAddress").mockResolvedValue({ ...HOME, city: "Achrafieh", area: null });
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Edit Home" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Edit address" })).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText(/^city/i));
    await user.type(within(dialog).getByLabelText(/^city/i), "Achrafieh");
    await user.clear(within(dialog).getByLabelText(/area \(optional\)/i));
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(update).toHaveBeenCalledWith("addr-1", { city: "Achrafieh", area: null });
    expect(await screen.findByText("Achrafieh, Beirut")).toBeInTheDocument();
    expect(screen.getByText("Address updated.")).toBeInTheDocument();
  });

  it("an edit with no changes sends no request", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME] });
    const update = vi.spyOn(addressesApi, "updateAddress");
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Edit Home" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(update).not.toHaveBeenCalled();
    expect(screen.getByText("No changes to save.")).toBeInTheDocument();
  });

  it("delete asks for confirmation; Cancel sends nothing; Confirm deletes, closes and refetches", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockResolvedValueOnce({ items: [HOME, WORK] });
    list.mockResolvedValue({ items: [HOME] });
    const del = vi.spyOn(addressesApi, "deleteAddress").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Delete Work" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/“Work”/);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(del).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete Work" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete address" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(del).toHaveBeenCalledWith("addr-2");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Work" })).not.toBeInTheDocument());
    expect(screen.getByText("Address deleted.")).toBeInTheDocument();
  });

  it("keeps the delete dialog open and busy while the request is pending, closing only once it succeeds", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME, WORK] });
    let finish!: () => void;
    vi.spyOn(addressesApi, "deleteAddress").mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Delete Work" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete address" }));

    const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Delete address" });
    expect(confirm).toHaveAttribute("aria-busy", "true");
    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("a 404 on edit (deleted elsewhere) closes the editor and explains, without the raw text", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME] });
    vi.spyOn(addressesApi, "updateAddress").mockRejectedValue(http(404, "NOT_FOUND"));
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Edit Home" }));
    await user.type(within(screen.getByRole("dialog")).getByLabelText(/^city/i), " East");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer exists/i);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
  });

  it("warns that deleting the default leaves no default", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME, WORK] });
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Delete Home" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/won't have a default address/i);
  });

  it("set as default calls PUT …/default and shows the server's new default after refetch", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockResolvedValueOnce({ items: [HOME, WORK] });
    list.mockResolvedValue({ items: [{ ...WORK, is_default: true }, { ...HOME, is_default: false }] });
    const setDefault = vi.spyOn(addressesApi, "setDefaultAddress").mockResolvedValue({ ...WORK, is_default: true });
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Set as default: Work" }));

    expect(setDefault).toHaveBeenCalledWith("addr-2");
    expect(await screen.findByRole("button", { name: "Set as default: Home" })).toBeInTheDocument();
    expect(screen.getByText("Default address updated.")).toBeInTheDocument();
  });

  it("a CSRF failure on a write shows the session copy, not the backend text", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME, WORK] });
    vi.spyOn(addressesApi, "setDefaultAddress").mockRejectedValue(http(403, "CSRF_INVALID"));
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Set as default: Work" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/unable to verify your session/i);
    expect(screen.queryByText(/RAW/)).not.toBeInTheDocument();
  });

  it("a 404 on delete (already gone) closes the dialog, explains, and refetches", async () => {
    const list = vi.spyOn(addressesApi, "listAddresses").mockResolvedValueOnce({ items: [HOME, WORK] });
    list.mockResolvedValue({ items: [HOME] });
    vi.spyOn(addressesApi, "deleteAddress").mockRejectedValue(http(404, "NOT_FOUND"));
    const user = userEvent.setup();
    renderBook();

    await user.click(await screen.findByRole("button", { name: "Delete Work" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete address" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer exists/i);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("an unverified customer sees why writes will be refused, with a link to resend verification", async () => {
    authAs(false);
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [] });
    renderBook();

    expect(await screen.findByText(/verify your email to add or change saved addresses/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /resend the verification email/i })).toHaveAttribute(
      "href",
      "/verify-email/resend"
    );
  });

  it("never shows shipping-zone, fee or free-shipping wording (ADR-024)", async () => {
    vi.spyOn(addressesApi, "listAddresses").mockResolvedValue({ items: [HOME, WORK] });
    renderBook();
    await screen.findByRole("heading", { name: "Home" });
    expect(screen.queryByText(/zone|shipping fee|free shipping/i)).not.toBeInTheDocument();
  });
});
