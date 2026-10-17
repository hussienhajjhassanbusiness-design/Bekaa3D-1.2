import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminSettingsPage from "./page";
import { useAdminSettings } from "@/lib/admin/settings/useAdminSettings";
import { useAdminSettingUpdate } from "@/lib/admin/settings/useAdminSettingUpdate";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";

vi.mock("@/lib/admin/settings/useAdminSettings", () => ({ useAdminSettings: vi.fn() }));
vi.mock("@/lib/admin/settings/useAdminSettingUpdate", () => ({ useAdminSettingUpdate: vi.fn() }));
const mockedUseAdminSettings = vi.mocked(useAdminSettings);
const mockedUseAdminSettingUpdate = vi.mocked(useAdminSettingUpdate);

const ACCEPTING_ORDERS: EditableSetting = {
  key: "accepting_orders",
  type: "boolean",
  label: "Accepting orders",
  description: "Whether new orders can be placed.",
  value: true,
};

const WHATSAPP_NUMBER: EditableSetting = {
  key: "whatsapp_number",
  type: "string",
  label: "Whatsapp number",
  value: "+96170000000",
  nullable: true,
};

function queryResult(overrides: Partial<ReturnType<typeof useAdminSettings>> = {}) {
  return { data: undefined, isLoading: false, isError: false, ...overrides } as ReturnType<typeof useAdminSettings>;
}

beforeEach(() => {
  mockedUseAdminSettings.mockReset();
  mockedUseAdminSettingUpdate.mockReset();
  mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync: vi.fn() } as never);
});

describe("AdminSettingsPage", () => {
  it("shows a loading state", () => {
    mockedUseAdminSettings.mockReturnValue(queryResult({ isLoading: true }));
    render(<AdminSettingsPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an error state", () => {
    mockedUseAdminSettings.mockReturnValue(queryResult({ isError: true }));
    render(<AdminSettingsPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders a row per setting, control chosen by type", () => {
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [ACCEPTING_ORDERS, WHATSAPP_NUMBER] }));
    render(<AdminSettingsPage />);

    expect(screen.getByRole("switch", { name: "Accepting orders" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Whatsapp number" })).toBeInTheDocument();
  });

  it("saving a non-sensitive setting calls the mutation directly, no confirmation", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync } as never);
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [WHATSAPP_NUMBER] }));
    const user = userEvent.setup();
    render(<AdminSettingsPage />);

    await user.clear(screen.getByRole("textbox", { name: "Whatsapp number" }));
    await user.type(screen.getByRole("textbox", { name: "Whatsapp number" }), "+96170000001");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({ key: "whatsapp_number", value: "+96170000001" })
    );
  });

  it("saving accepting_orders requires confirmation before the mutation runs", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync } as never);
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [ACCEPTING_ORDERS] }));
    const user = userEvent.setup();
    render(<AdminSettingsPage />);

    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm change/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ key: "accepting_orders", value: false }));
  });

  it("cancelling the confirmation dialog never calls the mutation", async () => {
    const mutateAsync = vi.fn();
    mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync } as never);
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [ACCEPTING_ORDERS] }));
    const user = userEvent.setup();
    render(<AdminSettingsPage />);

    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("shows a safe error message on a failed save", async () => {
    const mutateAsync = vi.fn().mockRejectedValue({ kind: "http", status: 422, code: "SETTING_INVALID", message: "x" });
    mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync } as never);
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [WHATSAPP_NUMBER] }));
    const user = userEvent.setup();
    render(<AdminSettingsPage />);

    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid value for this setting.");
  });

  it("links to the recovery-codes regeneration page", () => {
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [] }));
    render(<AdminSettingsPage />);
    expect(screen.getByRole("link", { name: /regenerate recovery codes/i })).toHaveAttribute(
      "href",
      "/admin/mfa/recovery-codes"
    );
  });
});
