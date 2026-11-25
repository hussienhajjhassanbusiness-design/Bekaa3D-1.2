import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminSettingsPage from "./page";
import { useAdminSettings } from "@/lib/admin/settings/useAdminSettings";
import { useAdminSettingUpdate } from "@/lib/admin/settings/useAdminSettingUpdate";
import type { RawSettingRead, RawSettingValue } from "@/lib/admin/settings/settingsAdapter";
import type { EditableSetting } from "@/components/admin/settings/settingTypes";
import { useHeroImage, useReplaceHeroImage, useRestoreDefaultHeroImage } from "@/lib/home/heroImageApi";

vi.mock("@/lib/admin/settings/useAdminSettings", () => ({ useAdminSettings: vi.fn() }));
vi.mock("@/lib/admin/settings/useAdminSettingUpdate", () => ({ useAdminSettingUpdate: vi.fn() }));
const mockedUseAdminSettings = vi.mocked(useAdminSettings);
const mockedUseAdminSettingUpdate = vi.mocked(useAdminSettingUpdate);
// The hero image hooks are mocked; the real constants and error copy are kept.
vi.mock("@/lib/home/heroImageApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/home/heroImageApi")>()),
  useHeroImage: vi.fn(),
  useReplaceHeroImage: vi.fn(),
  useRestoreDefaultHeroImage: vi.fn(),
}));
const mockedUseHeroImage = vi.mocked(useHeroImage);
const mockedUseReplaceHeroImage = vi.mocked(useReplaceHeroImage);
const mockedUseRestoreDefaultHeroImage = vi.mocked(useRestoreDefaultHeroImage);

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
  mockedUseHeroImage.mockReturnValue({ data: { url: null }, isError: false } as never);
  mockedUseReplaceHeroImage.mockReturnValue({ mutateAsync: vi.fn() } as never);
  mockedUseRestoreDefaultHeroImage.mockReturnValue({ mutateAsync: vi.fn() } as never);
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

// ---------------------------------------------------------------------------
// Homepage → Hero image (backend docs/homepage-hero-image.md)
// ---------------------------------------------------------------------------

const CURRENT_URL = "/media/home/hero/0123456789abcdef0123456789abcdef.webp";
const NEW_URL = "/media/home/hero/fedcba9876543210fedcba9876543210.png";
const HERO_SETTING: EditableSetting = {
  key: "homepage_hero_image",
  type: "string",
  label: "Homepage hero image",
  value: "home/hero/0123456789abcdef0123456789abcdef.webp",
  nullable: true,
};
const UPLOAD_REJECTED = { kind: "http", status: 422, code: "UPLOAD_REJECTED", message: "x" };

function pngFile(name = "eid-hero.png") {
  return new File(["png-bytes"], name, { type: "image/png" });
}

function renderHero({
  url = CURRENT_URL as string | null,
  replace = vi.fn(() => Promise.resolve({ url: NEW_URL })),
  settings = [...ALL_SETTINGS, HERO_SETTING],
  mutateAsync = echoMutate(),
  restore = vi.fn(() => Promise.resolve(savedRow("homepage_hero_image", null))),
}: {
  url?: string | null;
  replace?: ReturnType<typeof vi.fn>;
  settings?: EditableSetting[];
  mutateAsync?: ReturnType<typeof vi.fn>;
  restore?: ReturnType<typeof vi.fn>;
} = {}) {
  mockedUseHeroImage.mockReturnValue({ data: { url }, isError: false } as never);
  mockedUseReplaceHeroImage.mockReturnValue({ mutateAsync: replace } as never);
  mockedUseRestoreDefaultHeroImage.mockReturnValue({ mutateAsync: restore } as never);
  const view = renderWith(settings, mutateAsync);
  // Real browsers filter the picker by `accept`; a wrong file can still be
  // dropped or forced through, so this user doesn't apply it.
  const picker = userEvent.setup({ applyAccept: false });
  return { ...view, picker, replace, restore, homepage: () => screen.getByRole("region", { name: "Homepage" }) };
}

const heroInput = () => screen.getByLabelText("Hero image") as HTMLInputElement;

describe("AdminSettingsPage — homepage hero image", () => {
  beforeEach(() => {
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:preview-${++n}`);
    URL.revokeObjectURL = vi.fn();
  });

  it("shows the current saved image under Homepage, never as a typed setting", () => {
    const { homepage } = renderHero();

    const current = within(homepage()).getByRole("img", { name: "Current hero image" });
    expect(current).toHaveAttribute("src", CURRENT_URL);
    expect(current).toHaveClass("object-cover");
    expect(within(homepage()).getByText("Current image")).toBeInTheDocument();
    expect(within(homepage()).getByRole("button", { name: "Replace image" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /hero/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Other settings" })).not.toBeInTheDocument();
  });

  it("shows the default brand visual and Choose image when none is uploaded", () => {
    const { homepage } = renderHero({ url: null });
    expect(within(homepage()).getByRole("img", { name: "Default brand visual" })).toBeInTheDocument();
    expect(within(homepage()).getByText("Default brand visual (no image uploaded)")).toBeInTheDocument();
    expect(within(homepage()).getByRole("button", { name: "Choose image" })).toBeInTheDocument();
  });

  it("has no Homepage section when the backend has no hero image setting", () => {
    renderHero({ settings: ALL_SETTINGS });
    expect(screen.queryByRole("region", { name: "Homepage" })).not.toBeInTheDocument();
  });

  it("previews a chosen replacement locally and marks the form dirty, without uploading", async () => {
    const { picker, replace, homepage } = renderHero();
    expect(saveButton()).toBeDisabled();

    await picker.upload(heroInput(), pngFile());

    const preview = within(homepage()).getByRole("img", { name: "Preview of the new hero image" });
    expect(preview).toHaveAttribute("src", "blob:preview-1");
    expect(preview).toHaveClass("object-cover");
    expect(within(homepage()).queryByRole("img", { name: "Current hero image" })).not.toBeInTheDocument();
    expect(within(homepage()).getByText("New image — not saved yet")).toBeInTheDocument();
    expect(within(homepage()).getByText(/Selected: eid-hero\.png/)).toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("uploads the chosen image on Save, then shows Settings saved. and the stored image", async () => {
    const { user, picker, replace, mutateAsync, rerender } = renderHero();
    const file = pngFile();
    await picker.upload(heroInput(), file);

    await user.click(saveButton());

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith(file);
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(saveButton()).toBeDisabled();
    expect(screen.queryByText("New image — not saved yet")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview-1");

    // A refresh (the hook refetching) shows the newly stored image.
    mockedUseHeroImage.mockReturnValue({ data: { url: NEW_URL }, isError: false } as never);
    rerender(<AdminSettingsPage />);
    expect(screen.getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", NEW_URL);
  });

  it("saves typed settings and the hero image together in one Save", async () => {
    const { user, picker, replace, mutateAsync } = renderHero();
    await replaceText(user, "Pickup hours", "10-6");
    await picker.upload(heroInput(), pngFile());

    await user.click(saveButton());

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(mutateAsync).toHaveBeenCalledWith({ key: "pickup_hours", value: "10-6" });
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      "an unsupported type",
      () => new File(["GIF89a"], "anim.gif", { type: "image/gif" }),
      "isn't a supported file type",
    ],
    [
      "a file over 10 MB",
      () => Object.defineProperty(pngFile("huge.png"), "size", { value: 10 * 1024 * 1024 + 1 }),
      "is too large",
    ],
  ])("rejects %s locally: an inline error, nothing selected, nothing sent", async (_label, makeFile, reason) => {
    const { picker, replace, homepage } = renderHero();

    await picker.upload(heroInput(), makeFile());

    const alert = within(homepage()).getByRole("alert");
    expect(alert).toHaveTextContent(reason);
    expect(alert).toHaveTextContent("JPEG, PNG or WebP, up to 10 MB, at least 400 × 400 px.");
    expect(within(homepage()).getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", CURRENT_URL);
    expect(saveButton()).toBeDisabled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("a refused upload keeps the saved image, never claims success, and keeps the choice for a retry", async () => {
    const replace = vi.fn().mockRejectedValueOnce(UPLOAD_REJECTED).mockResolvedValueOnce({ url: NEW_URL });
    const { user, picker, homepage } = renderHero({ replace });
    await picker.upload(heroInput(), pngFile());

    await user.click(saveButton());

    const error = await within(homepage()).findByRole("alert");
    expect(error).toHaveTextContent("This image couldn't be used.");
    expect(error).toHaveTextContent("Your current hero image is unchanged.");
    expect(screen.getByRole("status")).not.toHaveTextContent("Settings saved.");
    expect(
      screen.getByText("Your changes couldn't be saved. Review the highlighted settings and try again.")
    ).toBeInTheDocument();
    expect(within(homepage()).getByText("New image — not saved yet")).toBeInTheDocument();
    expect(saveButton()).toBeEnabled();

    await user.click(saveButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(replace).toHaveBeenCalledTimes(2);
  });

  it("partial failure: a typed setting saved but the image refused is reported as partial", async () => {
    const replace = vi.fn().mockRejectedValue({ kind: "http", status: 503, code: "SERVICE_UNAVAILABLE", message: "x" });
    const { user, picker } = renderHero({ replace });
    await replaceText(user, "Pickup hours", "10-6");
    await picker.upload(heroInput(), pngFile());

    await user.click(saveButton());

    expect(
      await screen.findByText(
        "Some changes were saved, but others couldn't be. Review the highlighted settings and try again."
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/temporarily unavailable.*Your current hero image is unchanged\./)).toBeInTheDocument();
  });

  it("Keep current image and Discard changes drop the selection without a request", async () => {
    const { user, picker, replace, homepage } = renderHero();

    await picker.upload(heroInput(), pngFile());
    await user.click(within(homepage()).getByRole("button", { name: "Keep current image" }));
    expect(within(homepage()).getByRole("img", { name: "Current hero image" })).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();

    await picker.upload(heroInput(), pngFile("second.png"));
    expect(saveButton()).toBeEnabled();
    await user.click(discardButton());
    expect(within(homepage()).getByRole("img", { name: "Current hero image" })).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("is accessible: a labelled picker, a keyboard-reachable button, and still one Save", async () => {
    const { user, homepage } = renderHero();

    expect(heroInput()).toHaveAttribute("type", "file");
    expect(heroInput()).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(heroInput()).toHaveAccessibleDescription(/JPEG, PNG or WebP/);
    expect(within(homepage()).getByRole("heading", { level: 3, name: "Hero image" })).toBeInTheDocument();
    const click = vi.spyOn(heroInput(), "click");
    within(homepage()).getByRole("button", { name: "Replace image" }).focus();
    await user.keyboard("{Enter}");
    expect(click).toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: /save/i })).toHaveLength(1);
    expect(screen.getAllByRole("heading", { name: /settings/i })).toHaveLength(1);
  });
});

describe("AdminSettingsPage — restore the default hero visual", () => {
  beforeEach(() => {
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:preview-${++n}`);
    URL.revokeObjectURL = vi.fn();
  });

  const restoreButton = () => screen.queryByRole("button", { name: "Restore default" });

  it("is offered only when a custom image is saved or selected", async () => {
    const { picker, homepage } = renderHero({ url: null });
    expect(restoreButton()).not.toBeInTheDocument();

    await picker.upload(heroInput(), pngFile());
    expect(within(homepage()).getByRole("button", { name: "Restore default" })).toBeInTheDocument();
  });

  it("previews the default visual and marks the form dirty, without any request", async () => {
    const { user, restore, replace, mutateAsync, homepage } = renderHero();

    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    expect(within(homepage()).getByRole("img", { name: "Default brand visual" })).toHaveAttribute(
      "src",
      "/brand/bekaa3d-mark.png"
    );
    expect(within(homepage()).queryByRole("img", { name: "Current hero image" })).not.toBeInTheDocument();
    expect(within(homepage()).getByText("Default brand visual — not saved yet")).toBeInTheDocument();
    expect(restoreButton()).not.toBeInTheDocument();
    expect(within(homepage()).getByRole("button", { name: "Keep current image" })).toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(restore).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("Save sends the settings PATCH to null once, then shows Settings saved. and the default", async () => {
    const { user, restore, replace, mutateAsync, homepage, rerender } = renderHero();
    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    await user.click(saveButton());

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(restore).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalled();
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(saveButton()).toBeDisabled();

    // The hook's cache now reads null: the default, and nothing to restore.
    mockedUseHeroImage.mockReturnValue({ data: { url: null }, isError: false } as never);
    rerender(<AdminSettingsPage />);
    expect(within(homepage()).getByText("Default brand visual (no image uploaded)")).toBeInTheDocument();
    expect(restoreButton()).not.toBeInTheDocument();
  });

  it("Discard changes and Keep current image bring the saved image back without a request", async () => {
    const { user, restore, homepage } = renderHero();

    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));
    await user.click(discardButton());
    expect(within(homepage()).getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", CURRENT_URL);
    expect(saveButton()).toBeDisabled();

    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));
    await user.click(within(homepage()).getByRole("button", { name: "Keep current image" }));
    expect(within(homepage()).getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", CURRENT_URL);
    expect(saveButton()).toBeDisabled();
    expect(restore).not.toHaveBeenCalled();
  });

  it("a failed restore keeps the saved image and the pending restore, and a retry succeeds", async () => {
    const restore = vi
      .fn()
      .mockRejectedValueOnce({ kind: "network", message: "offline" })
      .mockResolvedValueOnce(savedRow("homepage_hero_image", null));
    const { user, homepage } = renderHero({ restore });
    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    await user.click(saveButton());

    const alert = await within(homepage()).findByRole("alert");
    expect(alert).toHaveTextContent("couldn't reach the server");
    expect(alert).toHaveTextContent("Your current hero image is unchanged.");
    expect(screen.getByRole("status")).not.toHaveTextContent("Settings saved.");
    expect(within(homepage()).getByText("Default brand visual — not saved yet")).toBeInTheDocument();
    expect(saveButton()).toBeEnabled();

    await user.click(saveButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(restore).toHaveBeenCalledTimes(2);
  });

  it("choosing another image after Restore default uploads that image instead", async () => {
    const { user, picker, restore, replace, homepage } = renderHero();
    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    const file = pngFile("ramadan.png");
    await picker.upload(heroInput(), file);
    expect(within(homepage()).getByRole("img", { name: "Preview of the new hero image" })).toBeInTheDocument();
    expect(within(homepage()).queryByText("Default brand visual — not saved yet")).not.toBeInTheDocument();

    await user.click(saveButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(replace).toHaveBeenCalledWith(file);
    expect(restore).not.toHaveBeenCalled();
  });

  it("Restore default after choosing a file drops the file and restores instead", async () => {
    const { user, picker, restore, replace, homepage } = renderHero();
    await picker.upload(heroInput(), pngFile());

    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));
    expect(within(homepage()).getByText("Default brand visual — not saved yet")).toBeInTheDocument();
    expect(within(homepage()).queryByText(/Selected:/)).not.toBeInTheDocument();

    await user.click(saveButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Settings saved."));
    expect(restore).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalled();
  });

  it("with no saved image, Restore default just drops the chosen file: nothing to save", async () => {
    const { user, picker, restore, homepage } = renderHero({ url: null });
    await picker.upload(heroInput(), pngFile());

    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    expect(within(homepage()).getByText("Default brand visual (no image uploaded)")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    expect(restore).not.toHaveBeenCalled();
  });

  it("partial failure: a typed setting saved but the restore refused is reported as partial", async () => {
    const restore = vi.fn().mockRejectedValue({ kind: "http", status: 503, code: "SERVICE_UNAVAILABLE", message: "x" });
    const { user, homepage } = renderHero({ restore });
    await replaceText(user, "Pickup hours", "10-6");
    await user.click(within(homepage()).getByRole("button", { name: "Restore default" }));

    await user.click(saveButton());

    expect(
      await screen.findByText(
        "Some changes were saved, but others couldn't be. Review the highlighted settings and try again."
      )
    ).toBeInTheDocument();
    expect(within(homepage()).getByText("Default brand visual — not saved yet")).toBeInTheDocument();
  });
});
