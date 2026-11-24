import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminSettingsPage from "./page";
import { useAdminSettings } from "@/lib/admin/settings/useAdminSettings";
import { useAdminSettingUpdate } from "@/lib/admin/settings/useAdminSettingUpdate";
import type { RawSettingRead, RawSettingValue } from "@/lib/admin/settings/settingsAdapter";
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
const CASH_PAYMENT_ENABLED: EditableSetting = {
  key: "cash_payment_enabled",
  type: "boolean",
  label: "Cash payment enabled",
  value: true,
};
const CASH_MAX_ORDER_TOTAL: EditableSetting = {
  key: "cash_max_order_total",
  type: "money",
  label: "Cash max order total",
  value: { amountCents: 10000, currency: "USD" },
};
const PICKUP_ADDRESS: EditableSetting = {
  key: "pickup_address",
  type: "string",
  label: "Pickup address",
  value: "Zahle main road",
  nullable: true,
};
const PICKUP_HOURS: EditableSetting = {
  key: "pickup_hours",
  type: "string",
  label: "Pickup hours",
  value: "9-5",
  nullable: true,
};
const WHATSAPP_NUMBER: EditableSetting = {
  key: "whatsapp_number",
  type: "string",
  label: "Whatsapp number",
  value: "+96170000000",
  nullable: true,
};
const ALL_SETTINGS = [
  ACCEPTING_ORDERS,
  CASH_PAYMENT_ENABLED,
  CASH_MAX_ORDER_TOTAL,
  PICKUP_ADDRESS,
  PICKUP_HOURS,
  WHATSAPP_NUMBER,
];

const INVALID_ERROR = { kind: "http", status: 422, code: "SETTING_INVALID", message: "x" };

// What the backend returns from a successful PATCH (schema SettingRead).
function savedRow(key: string, value: RawSettingValue, type: RawSettingRead["type"] = "string"): RawSettingRead {
  return {
    key,
    type,
    value,
    description: null,
    unit: null,
    minimum: null,
    maximum: null,
    nullable: true,
    is_public: true,
    updated_at: "2026-11-24T00:00:00Z",
    updated_by: null,
  };
}

// Echoes each PATCH back as the stored row, like the real backend.
const echoMutate = () =>
  vi.fn(({ key, value }: { key: string; value: RawSettingValue }) =>
    Promise.resolve(savedRow(key, value, typeof value === "boolean" ? "boolean" : "string"))
  );

function queryResult(overrides: Partial<ReturnType<typeof useAdminSettings>> = {}) {
  return { data: undefined, isLoading: false, isError: false, ...overrides } as ReturnType<typeof useAdminSettings>;
}

function renderWith(settings: EditableSetting[], mutateAsync: ReturnType<typeof vi.fn> = echoMutate()) {
  mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync } as never);
  mockedUseAdminSettings.mockReturnValue(queryResult({ data: settings }));
  const user = userEvent.setup();
  const view = render(<AdminSettingsPage />);
  return { user, mutateAsync, ...view };
}

const saveButton = () => screen.getByRole("button", { name: "Save changes" });
const discardButton = () => screen.getByRole("button", { name: "Discard changes" });

async function replaceText(user: ReturnType<typeof userEvent.setup>, name: string, text: string) {
  const input = screen.getByRole("textbox", { name });
  await user.clear(input);
  await user.type(input, text);
}

beforeEach(() => {
  mockedUseAdminSettings.mockReset();
  mockedUseAdminSettingUpdate.mockReset();
  mockedUseAdminSettingUpdate.mockReturnValue({ mutateAsync: vi.fn() } as never);
});

describe("AdminSettingsPage — loading", () => {
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

  it("loads the current settings into grouped sections, control chosen by type", () => {
    renderWith(ALL_SETTINGS);

    const availability = screen.getByRole("region", { name: "Store availability" });
    expect(within(availability).getByRole("switch", { name: "Accepting orders" })).toHaveAttribute(
      "aria-checked",
      "true"
    );
    const payments = screen.getByRole("region", { name: "Payments" });
    expect(within(payments).getByRole("switch", { name: "Cash payment enabled" })).toBeInTheDocument();
    expect(within(payments).getByRole("textbox", { name: /cash max order total/i })).toHaveValue("100.00");
    const pickup = screen.getByRole("region", { name: "Pickup" });
    expect(within(pickup).getByRole("textbox", { name: "Pickup address" })).toHaveValue("Zahle main road");
    expect(within(pickup).getByRole("textbox", { name: "Pickup hours" })).toHaveValue("9-5");
    const contact = screen.getByRole("region", { name: "Contact" });
    expect(within(contact).getByRole("textbox", { name: "Whatsapp number" })).toHaveValue("+96170000000");
  });

  it("keeps any other server setting visible under Other settings", () => {
    const holdPeriod: EditableSetting = {
      key: "checkout_hold_period",
      type: "number",
      label: "Checkout hold period",
      value: 1800,
    };
    renderWith([ACCEPTING_ORDERS, holdPeriod]);
    const other = screen.getByRole("region", { name: "Other settings" });
    expect(within(other).getByRole("spinbutton", { name: /checkout hold period/i })).toHaveValue(1800);
  });

  // Playwright's getByRole name match is a substring match: a second heading
  // containing "Settings" (e.g. a hidden "Store settings" form heading) made
  // the admin-routes E2E spec ambiguous.
  it("has only one heading whose name contains Settings", () => {
    renderWith(ALL_SETTINGS);
    expect(screen.getAllByRole("heading", { name: /settings/i })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  });

  it("renders exactly one Save changes button, no per-field Save", () => {
    renderWith(ALL_SETTINGS);
    expect(screen.getAllByRole("button", { name: /save/i })).toHaveLength(1);
  });
});

describe("AdminSettingsPage — dirty state", () => {
  it("disables Save and Discard while nothing has changed", () => {
    renderWith(ALL_SETTINGS);
    expect(saveButton()).toBeDisabled();
    expect(discardButton()).toBeDisabled();
  });

  it("enables Save as soon as one field changes, and disables it again when the edit is reverted", async () => {
    const { user } = renderWith(ALL_SETTINGS);

    await user.click(screen.getByRole("switch", { name: "Cash payment enabled" }));
    expect(saveButton()).toBeEnabled();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "Cash payment enabled" }));
    expect(saveButton()).toBeDisabled();
  });

  it("keeps an unsaved edit when server data refreshes, while clean fields adopt the new server value", async () => {
    const { user, rerender } = renderWith(ALL_SETTINGS);
    await replaceText(user, "Pickup hours", "10-6");

    mockedUseAdminSettings.mockReturnValue(
      queryResult({
        data: ALL_SETTINGS.map((setting) =>
          setting.key === "pickup_address"
            ? { ...PICKUP_ADDRESS, value: "New address" }
            : setting.key === "pickup_hours"
              ? { ...PICKUP_HOURS, value: "8-4" }
              : setting
        ),
      })
    );
    rerender(<AdminSettingsPage />);

    expect(screen.getByRole("textbox", { name: "Pickup hours" })).toHaveValue("10-6");
    expect(screen.getByRole("textbox", { name: "Pickup address" })).toHaveValue("New address");
    expect(saveButton()).toBeEnabled();
  });
});

describe("AdminSettingsPage — saving", () => {
  it("saves several changed fields with one Save click, sending only the changed keys", async () => {
    const { user, mutateAsync } = renderWith(ALL_SETTINGS);

    await user.click(screen.getByRole("switch", { name: "Cash payment enabled" }));
    await replaceText(user, "Pickup hours", "10-6");
    await replaceText(user, "Whatsapp number", "+96170000001");
    await user.click(saveButton());

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
    expect(mutateAsync).toHaveBeenCalledWith({ key: "cash_payment_enabled", value: false });
    expect(mutateAsync).toHaveBeenCalledWith({ key: "pickup_hours", value: "10-6" });
    expect(mutateAsync).toHaveBeenCalledWith({ key: "whatsapp_number", value: "+96170000001" });
    const sentKeys = mutateAsync.mock.calls.map(([args]) => (args as { key: string }).key);
    expect(sentKeys).not.toContain("accepting_orders");
    expect(sentKeys).not.toContain("pickup_address");
    expect(sentKeys).not.toContain("cash_max_order_total");
  });

  it("shows Settings saved. in a polite status and clears the dirty state after success", async () => {
    const { user } = renderWith(ALL_SETTINGS);

    await replaceText(user, "Pickup hours", "10-6");
    await user.click(saveButton());

    const status = await screen.findByText("Settings saved.");
    expect(status.closest("[role=status]")).toHaveAttribute("aria-live", "polite");
    expect(saveButton()).toBeDisabled();
    expect(discardButton()).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Pickup hours" })).toHaveValue("10-6");
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("reconciles a saved field with the value the server actually stored", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(savedRow("pickup_hours", "10:00-18:00"));
    const { user } = renderWith(ALL_SETTINGS, mutateAsync);

    await replaceText(user, "Pickup hours", "10-6");
    await user.click(saveButton());

    await screen.findByText("Settings saved.");
    expect(screen.getByRole("textbox", { name: "Pickup hours" })).toHaveValue("10:00-18:00");
    expect(saveButton()).toBeDisabled();
  });

  it("shows Saving… and ignores repeat clicks while a save is in flight", async () => {
    let resolve: (row: RawSettingRead) => void = () => undefined;
    const mutateAsync = vi.fn(() => new Promise<RawSettingRead>((r) => (resolve = r)));
    const { user } = renderWith(ALL_SETTINGS, mutateAsync);

    await replaceText(user, "Pickup hours", "10-6");
    await user.click(saveButton());

    expect(await screen.findByText("Saving…")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    expect(saveButton()).toHaveAttribute("aria-busy", "true");
    await user.click(saveButton());
    await user.click(saveButton());
    expect(mutateAsync).toHaveBeenCalledTimes(1);

    resolve(savedRow("pickup_hours", "10-6"));
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  it("a failed save keeps the edited value, shows a safe error, and allows retry", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce(INVALID_ERROR)
      .mockResolvedValueOnce(savedRow("whatsapp_number", "+96170000009"));
    const { user } = renderWith(ALL_SETTINGS, mutateAsync);

    await replaceText(user, "Whatsapp number", "070-000");
    await user.click(saveButton());

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.map((alert) => alert.textContent)).toEqual(
      expect.arrayContaining([
        "Enter a valid value for this setting.",
        "Your changes couldn't be saved. Review the highlighted settings and try again.",
      ])
    );
    expect(screen.queryByText("Settings saved.")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Whatsapp number" })).toHaveValue("070-000");
    expect(saveButton()).toBeEnabled();

    await replaceText(user, "Whatsapp number", "+96170000009");
    await user.click(saveButton());

    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("partial failure: never claims success, keeps the failed edit dirty, and retries only the failed key", async () => {
    const mutateAsync = vi.fn(({ key, value }: { key: string; value: RawSettingValue }) =>
      key === "whatsapp_number" ? Promise.reject(INVALID_ERROR) : Promise.resolve(savedRow(key, value))
    );
    const { user } = renderWith(ALL_SETTINGS, mutateAsync);

    await replaceText(user, "Pickup hours", "10-6");
    await replaceText(user, "Whatsapp number", "070-000");
    await user.click(saveButton());

    expect(
      await screen.findByText(
        "Some changes were saved, but others couldn't be. Review the highlighted settings and try again."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("Settings saved.")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Pickup hours" })).toHaveValue("10-6");
    expect(screen.getByRole("textbox", { name: "Whatsapp number" })).toHaveValue("070-000");
    expect(saveButton()).toBeEnabled();

    mutateAsync.mockClear();
    await user.click(saveButton());
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({ key: "whatsapp_number", value: "070-000" });
  });
});

describe("AdminSettingsPage — accepting_orders confirmation", () => {
  it("requires confirmation before any request when accepting_orders is among the changes", async () => {
    const { user, mutateAsync } = renderWith(ALL_SETTINGS);

    await user.click(screen.getByRole("switch", { name: "Accepting orders" }));
    await replaceText(user, "Pickup hours", "10-6");
    await user.click(saveButton());

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm change/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync).toHaveBeenCalledWith({ key: "accepting_orders", value: false });
    expect(mutateAsync).toHaveBeenCalledWith({ key: "pickup_hours", value: "10-6" });
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
  });

  it("cancelling the confirmation never calls the mutation and keeps the edits", async () => {
    const { user, mutateAsync } = renderWith(ALL_SETTINGS);

    await user.click(screen.getByRole("switch", { name: "Accepting orders" }));
    await user.click(saveButton());
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "Accepting orders" })).toHaveAttribute("aria-checked", "false");
    expect(saveButton()).toBeEnabled();
  });

  it("does not ask for confirmation when accepting_orders is unchanged", async () => {
    const { user, mutateAsync } = renderWith(ALL_SETTINGS);

    await replaceText(user, "Pickup address", "Chtaura");
    await user.click(saveButton());

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ key: "pickup_address", value: "Chtaura" }));
  });
});

describe("AdminSettingsPage — discard", () => {
  it("resets every edit to the saved values without any request", async () => {
    const { user, mutateAsync } = renderWith(ALL_SETTINGS);

    await user.click(screen.getByRole("switch", { name: "Cash payment enabled" }));
    await replaceText(user, "Pickup hours", "10-6");
    await user.click(discardButton());

    expect(screen.getByRole("switch", { name: "Cash payment enabled" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("textbox", { name: "Pickup hours" })).toHaveValue("9-5");
    expect(saveButton()).toBeDisabled();
    expect(discardButton()).toBeDisabled();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("resets the money field's displayed text too", async () => {
    const { user } = renderWith(ALL_SETTINGS);
    const money = screen.getByRole("textbox", { name: /cash max order total/i });

    await user.clear(money);
    await user.type(money, "250");
    expect(saveButton()).toBeEnabled();
    await user.click(discardButton());

    expect(money).toHaveValue("100.00");
  });
});

describe("AdminSettingsPage — security", () => {
  it("links to the recovery-codes regeneration page", () => {
    mockedUseAdminSettings.mockReturnValue(queryResult({ data: [] }));
    render(<AdminSettingsPage />);
    expect(screen.getByRole("link", { name: /regenerate recovery codes/i })).toHaveAttribute(
      "href",
      "/admin/mfa/recovery-codes"
    );
  });
});
