import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DefaultAddressSelector } from "./DefaultAddressSelector";

// FVS-023-IMPLEMENTATION-PLAN.md T03 — a real radio group (never
// independent checkboxes/switches), since only one address can ever
// be the default. Named DefaultAddressSelector rather than
// SetDefaultToggle to avoid implying toggle/checkbox semantics it must
// not have — accessibility wins over the plan's literal component
// name.

const OPTIONS = [
  { id: "addr-1", label: "Jane Doe, Main Street, Beirut", isDefault: true },
  { id: "addr-2", label: "John Doe, Second Street, Tripoli", isDefault: false },
  { id: "addr-3", label: "Alex Doe, Third Street, Sidon", isDefault: false },
];

describe("DefaultAddressSelector", () => {
  it("renders exactly one radio group", () => {
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("group", { name: /default address/i })).toBeInTheDocument();
  });

  it("gives each option a clear, distinct accessible label", () => {
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} />);
    for (const option of OPTIONS) {
      expect(screen.getByRole("radio", { name: option.label })).toBeInTheDocument();
    }
  });

  it("checks exactly the current default, and no other option", () => {
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const checked = radios.filter((r) => r.checked);
    expect(checked).toHaveLength(1);
    expect(screen.getByRole("radio", { name: OPTIONS[0]!.label })).toBeChecked();
  });

  it("calls onSelect with the chosen address id when a different option is picked", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<DefaultAddressSelector options={OPTIONS} onSelect={onSelect} />);

    await user.click(screen.getByRole("radio", { name: OPTIONS[1]!.label }));

    expect(onSelect).toHaveBeenCalledWith("addr-2");
  });

  it("disables every option and announces a pending status while a switch is in flight", () => {
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} pendingId="addr-2" />);

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByRole("status")).toHaveTextContent(/updating/i);
  });

  it("never removes an option's accessible label while pending", () => {
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} pendingId="addr-2" />);

    for (const option of OPTIONS) {
      expect(screen.getByRole("radio", { name: option.label })).toBeInTheDocument();
    }
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<DefaultAddressSelector options={OPTIONS} onSelect={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
