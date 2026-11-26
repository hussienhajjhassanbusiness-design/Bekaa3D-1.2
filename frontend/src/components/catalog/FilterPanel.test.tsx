import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterPanel } from "./FilterPanel";
import type { FacetGroup } from "./FilterPanel";

// FVS-013-IMPLEMENTATION-PLAN.md T02 — generic, presentational facet
// panel. No fetch, no hardcoded facet entries — category/material/
// colour options always come from the `groups` prop (proven below by
// using deliberately non-domain group/option names).

const GROUPS: FacetGroup[] = [
  {
    id: "widget-kind",
    legend: "Widget kind",
    options: [
      { value: "alpha", label: "Alpha", checked: false },
      { value: "beta", label: "Beta", checked: true },
    ],
  },
  {
    id: "widget-hue",
    legend: "Widget hue",
    options: [{ value: "red", label: "Red", checked: false }],
  },
];

describe("FilterPanel", () => {
  it("renders a fieldset/legend per facet group", () => {
    render(<FilterPanel groups={GROUPS} onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Widget kind" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Widget hue" })).toBeInTheDocument();
  });

  it("renders real native checkboxes with visible text labels", () => {
    render(<FilterPanel groups={GROUPS} onChange={vi.fn()} />);
    const checkbox = screen.getByRole("checkbox", { name: "Alpha" });
    expect(checkbox).toHaveAttribute("type", "checkbox");
  });

  it("reflects each option's checked state", () => {
    render(<FilterPanel groups={GROUPS} onChange={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "Alpha" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeChecked();
  });

  it("calls onChange with the group id, option value, and next checked state", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<FilterPanel groups={GROUPS} onChange={onChange} />);

    await user.click(screen.getByRole("checkbox", { name: "Alpha" }));

    expect(onChange).toHaveBeenCalledWith("widget-kind", "alpha", true);
  });

  it("renders a safe message for an empty facet group instead of crashing", () => {
    render(<FilterPanel groups={[{ id: "empty-group", legend: "Empty group", options: [] }]} onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Empty group" })).toBeInTheDocument();
    expect(screen.getByText(/no options available/i)).toBeInTheDocument();
  });

  it("keeps a colour-style facet's labels textual, never color-only", () => {
    render(
      <FilterPanel
        groups={[{ id: "colour", legend: "Colour", options: [{ value: "red", label: "Red", checked: false }] }]}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByText("Red")).toBeInTheDocument();
  });

  it("renders applied filter chips, each removable with a clear accessible name", async () => {
    const onRemoveFilter = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterPanel
        groups={GROUPS}
        onChange={vi.fn()}
        appliedFilters={[{ groupId: "widget-kind", value: "beta", label: "Beta" }]}
        onRemoveFilter={onRemoveFilter}
      />
    );

    await user.click(screen.getByRole("button", { name: "Remove Beta filter" }));

    expect(onRemoveFilter).toHaveBeenCalledWith("widget-kind", "beta");
  });

  it("calls onClearAll when the clear-filters action is activated", async () => {
    const onClearAll = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterPanel
        groups={GROUPS}
        onChange={vi.fn()}
        appliedFilters={[{ groupId: "widget-kind", value: "beta", label: "Beta" }]}
        onClearAll={onClearAll}
      />
    );

    await user.click(screen.getByRole("button", { name: /clear filters/i }));

    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<FilterPanel groups={GROUPS} onChange={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<FilterPanel groups={GROUPS} onChange={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
