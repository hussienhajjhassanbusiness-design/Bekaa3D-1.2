import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchableCombobox } from "./SearchableCombobox";
import type { ComboboxOption } from "./SearchableCombobox";

// FVS-019-IMPLEMENTATION-PLAN.md T02 — a small, fully keyboard-
// accessible single-select combobox, built because no existing
// accessible combobox/dependency was found in the repository (audited
// first — a large UI package was not installed solely for this).
// Filtering is purely local (substring match over the already-supplied
// `options` prop) — this is NOT a backend search call; a future real,
// debounced server-search integration stays contract-gated, same
// precedent as FVS-013's SearchBar.

const OPTIONS: ComboboxOption[] = [
  { id: "c-1", label: "Ada Lovelace" },
  { id: "c-2", label: "Grace Hopper" },
  { id: "c-3", label: "Alan Turing" },
];

describe("SearchableCombobox", () => {
  it("has a programmatic label", () => {
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Customer")).toBeInTheDocument();
  });

  it("exposes role=combobox with aria-expanded reflecting open state", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    const input = screen.getByRole("combobox");
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.click(input);
    await user.type(input, "a");

    expect(input).toHaveAttribute("aria-expanded", "true");
  });

  it("aria-controls points to the real listbox element", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    const input = screen.getByRole("combobox");
    await user.type(input, "a");

    const listboxId = input.getAttribute("aria-controls");
    expect(listboxId).toBeTruthy();
    expect(document.getElementById(listboxId!)).toHaveAttribute("role", "listbox");
  });

  it("filters visible options as the user types", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);

    await user.type(screen.getByRole("combobox"), "grace");

    expect(screen.getByRole("option", { name: "Grace Hopper" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Ada Lovelace" })).not.toBeInTheDocument();
  });

  it("selects an option via keyboard only (ArrowDown then Enter), no mouse required", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={onChange} />);
    const input = screen.getByRole("combobox");

    await user.click(input);
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("c-1");
  });

  it("shows the selected option's label in the input after selection", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    const input = screen.getByRole("combobox");

    await user.click(input);
    await user.keyboard("{ArrowDown}{Enter}");

    expect(input).toHaveValue("Ada Lovelace");
  });

  it("Escape closes the listbox without selecting or calling onChange", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={onChange} />);
    const input = screen.getByRole("combobox");

    await user.type(input, "a");
    await user.keyboard("{Escape}");

    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("also supports selecting an option by clicking it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={onChange} />);

    await user.type(screen.getByRole("combobox"), "grace");
    await user.click(screen.getByRole("option", { name: "Grace Hopper" }));

    expect(onChange).toHaveBeenCalledWith("c-2");
  });

  it("shows a safe empty state when no option matches", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);

    await user.type(screen.getByRole("combobox"), "zzz-no-match");

    expect(screen.getByText(/no results/i)).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("marks the keyboard-active option via aria-activedescendant", async () => {
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    const input = screen.getByRole("combobox");

    await user.click(input);
    await user.keyboard("{ArrowDown}");

    const activeId = input.getAttribute("aria-activedescendant");
    expect(activeId).toBeTruthy();
    expect(document.getElementById(activeId!)).toHaveTextContent("Ada Lovelace");
  });

  it("never makes a network/fetch call", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    await user.type(screen.getByRole("combobox"), "a");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<SearchableCombobox label="Customer" options={OPTIONS} value={null} onChange={vi.fn()} />);
    await user.type(screen.getByRole("combobox"), "a");
    expect(spy).not.toHaveBeenCalled();
  });
});
