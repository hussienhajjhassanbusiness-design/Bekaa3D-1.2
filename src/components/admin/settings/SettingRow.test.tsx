import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingRow } from "./SettingRow";
import type { BooleanSetting, NumberSetting } from "./settingTypes";

// FVS-007-IMPLEMENTATION-PLAN.md T03 — label + description + SettingControl
// + save seam + status/error presentation, responsive per the confirmed
// (FRONTEND-VERTICAL-SLICE-PLAN.md) stacked-card convention. status/
// errorMessage are external, already-safe props — this component never
// parses a raw backend error itself, and never awaits onSave's return
// value (the real pending/error state will live in a future mutation
// hook, not here).

const BOOLEAN_SETTING: BooleanSetting = {
  key: "accepting-orders",
  type: "boolean",
  label: "Accepting orders",
  description: "Whether new orders can be placed.",
  value: true,
};

const NUMBER_SETTING: NumberSetting = {
  key: "offer-floor",
  type: "number",
  label: "Offer floor",
  value: 10,
};

describe("SettingRow", () => {
  it("renders the label", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(screen.getByText("Accepting orders")).toBeInTheDocument();
  });

  it("renders the description", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(screen.getByText("Whether new orders can be placed.")).toBeInTheDocument();
  });

  it("renders the appropriate SettingControl for the setting's declared type", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("renders a numeric control for a number setting", () => {
    render(<SettingRow setting={NUMBER_SETTING} onSave={vi.fn()} />);
    expect(screen.getByRole("spinbutton")).toBeInTheDocument();
  });

  it("save calls onSave with the current (possibly edited) typed value, not the original", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={onSave} />);

    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(onSave).toHaveBeenCalledWith(false);
  });

  it("disables Save while status is 'saving'", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} status="saving" />);
    expect(screen.getByRole("button", { name: /sav/i })).toBeDisabled();
  });

  it("does not call onSave when clicking a disabled Save button while saving", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={onSave} status="saving" />);

    await user.click(screen.getByRole("button", { name: /sav/i }));

    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows the exact passed-in safe error message near the control when status is 'error'", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} status="error" errorMessage="That value is out of range." />);

    expect(screen.getByRole("alert")).toHaveTextContent("That value is out of range.");
  });

  it("never invents or renders anything beyond the exact safe error message given", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} status="error" errorMessage="Safe message." />);

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toBe("Safe message.");
  });

  it("shows no error alert when status is idle", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("carries responsive stacking structure classes for mobile and the row/table-like structure for tablet+", () => {
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    const row = screen.getByTestId("setting-row");
    expect(row.className).toMatch(/flex-col/);
    expect(row.className).toMatch(/tablet:flex-row/);
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SettingRow setting={BOOLEAN_SETTING} onSave={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
