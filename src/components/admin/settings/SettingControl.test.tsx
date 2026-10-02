import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingControl } from "./SettingControl";
import type { BooleanSetting, EditableSetting, NumberSetting, StringSetting } from "./settingTypes";

// A small stateful harness — SettingControl is a controlled component, so
// simulating multiple keystrokes with userEvent requires actually feeding
// each onChange back into the displayed value (otherwise the DOM value
// keeps snapping back to the original prop between keystrokes, which is
// a controlled-input testing pitfall, not a SettingControl defect).
function ControlledHarness({
  initial,
  onChange,
}: {
  initial: EditableSetting;
  onChange: (value: EditableSetting["value"]) => void;
}) {
  const [setting, setSetting] = useState(initial);
  return (
    <SettingControl
      setting={setting}
      onChange={(value) => {
        onChange(value);
        setSetting((current) => ({ ...current, value }) as EditableSetting);
      }}
    />
  );
}

// FVS-007-IMPLEMENTATION-PLAN.md T02 — the one renderer that picks the
// right native control by declared type. Pure presentation: no network
// calls, no server-state ownership, no browser persistence, no raw JSON
// editor. `setting` is the frontend-normalized EditableSetting UI model
// (settingTypes.ts) — never a claim about the real backend response.

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
  description: "Minimum accepted offer, in whole currency units.",
  value: 10,
  min: 0,
  max: 1000,
  step: 1,
};

const STRING_SETTING: StringSetting = {
  key: "whatsapp-number",
  type: "string",
  label: "WhatsApp number",
  value: "+96112345678",
};

describe("SettingControl", () => {
  describe("boolean", () => {
    it("renders a switch", () => {
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("switch")).toBeInTheDocument();
    });

    it("has a correct accessible label", () => {
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("switch", { name: "Accepting orders" })).toBeInTheDocument();
    });

    it("reflects the current value via aria-checked", () => {
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
    });

    it("reflects a false value via aria-checked", () => {
      render(<SettingControl setting={{ ...BOOLEAN_SETTING, value: false }} onChange={vi.fn()} />);
      expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
    });

    it("is keyboard-activatable (a real native button, not a div)", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={onChange} />);

      const switchEl = screen.getByRole("switch");
      expect(switchEl.tagName).toBe("BUTTON");
      switchEl.focus();
      await user.keyboard(" ");

      expect(onChange).toHaveBeenCalledWith(false);
    });

    it("calls onChange with the exact next boolean on click", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={onChange} />);

      await user.click(screen.getByRole("switch"));

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(false);
    });

    it("associates the description via aria-describedby", () => {
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={vi.fn()} />);
      const switchEl = screen.getByRole("switch");
      const describedBy = switchEl.getAttribute("aria-describedby");
      expect(describedBy).toBeTruthy();
      expect(document.getElementById(describedBy!)).toHaveTextContent("Whether new orders can be placed.");
    });
  });

  describe("number", () => {
    it("renders a numeric input", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("spinbutton")).toBeInTheDocument();
    });

    it("displays the exact numeric value", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("spinbutton")).toHaveValue(10);
    });

    it("propagates min when provided", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("spinbutton")).toHaveAttribute("min", "0");
    });

    it("propagates max when provided", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("spinbutton")).toHaveAttribute("max", "1000");
    });

    it("propagates step when provided", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("spinbutton")).toHaveAttribute("step", "1");
    });

    it("omits min/max/step entirely when not provided", () => {
      const withoutConstraints: NumberSetting = { ...NUMBER_SETTING, min: undefined, max: undefined, step: undefined };
      render(<SettingControl setting={withoutConstraints} onChange={vi.fn()} />);
      const input = screen.getByRole("spinbutton");
      expect(input).not.toHaveAttribute("min");
      expect(input).not.toHaveAttribute("max");
      expect(input).not.toHaveAttribute("step");
    });

    it("calls onChange with a real number, not a string, on edit", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<ControlledHarness initial={NUMBER_SETTING} onChange={onChange} />);

      const input = screen.getByRole("spinbutton");
      await user.clear(input);
      await user.type(input, "42");

      expect(onChange).toHaveBeenLastCalledWith(42);
      expect(typeof onChange.mock.calls.at(-1)?.[0]).toBe("number");
    });

    it("has an accessible label and description association", () => {
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      const input = screen.getByRole("spinbutton", { name: "Offer floor" });
      const describedBy = input.getAttribute("aria-describedby");
      expect(describedBy).toBeTruthy();
      expect(document.getElementById(describedBy!)).toHaveTextContent(/minimum accepted offer/i);
    });
  });

  describe("string", () => {
    it("renders a text input", () => {
      render(<SettingControl setting={STRING_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("textbox")).toBeInTheDocument();
    });

    it("displays the exact string value", () => {
      render(<SettingControl setting={STRING_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("textbox")).toHaveValue("+96112345678");
    });

    it("does not trim or normalize the value as the user types", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<ControlledHarness initial={{ ...STRING_SETTING, value: "" }} onChange={onChange} />);

      await user.type(screen.getByRole("textbox"), "  spaced  ");

      expect(onChange).toHaveBeenLastCalledWith("  spaced  ");
    });

    it("has an accessible label", () => {
      render(<SettingControl setting={STRING_SETTING} onChange={vi.fn()} />);
      expect(screen.getByRole("textbox", { name: "WhatsApp number" })).toBeInTheDocument();
    });
  });

  describe("general", () => {
    it("never makes a network/fetch call", () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch");
      render(<SettingControl setting={BOOLEAN_SETTING} onChange={vi.fn()} />);
      expect(fetchSpy).not.toHaveBeenCalled();
      fetchSpy.mockRestore();
    });

    it("never writes to localStorage or sessionStorage", () => {
      const localSpy = vi.spyOn(Storage.prototype, "setItem");
      render(<SettingControl setting={NUMBER_SETTING} onChange={vi.fn()} />);
      expect(localSpy).not.toHaveBeenCalled();
      localSpy.mockRestore();
    });

    it("never renders a raw JSON editor (no textarea, no JSON.stringify output)", () => {
      render(<SettingControl setting={STRING_SETTING} onChange={vi.fn()} />);
      expect(document.querySelectorAll("textarea")).toHaveLength(0);
      expect(document.body.textContent).not.toContain("{");
    });
  });
});
