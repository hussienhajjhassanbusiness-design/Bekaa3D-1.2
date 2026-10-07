import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SortSelect } from "./SortSelect";

// FVS-013-IMPLEMENTATION-PLAN.md T03 — allowlisted sort control.
// Options are ALWAYS data-driven from the `options` prop — this
// component never renders a sort value (e.g. "most-downloaded") that
// the caller didn't explicitly supply, since VS-013 only confirms sort
// is allowlisted/backend-restricted, not which exact values exist.

const OPTIONS = [
  { value: "relevance", label: "Relevance" },
  { value: "newest", label: "Newest" },
];

describe("SortSelect", () => {
  it("renders a native select", () => {
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} />);
    expect(screen.getByRole("combobox").tagName).toBe("SELECT");
  });

  it("has an accessible label", () => {
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} />);
    expect(screen.getByLabelText("Sort by")).toBeInTheDocument();
  });

  it("supports a custom accessible label", () => {
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} label="Order results by" />);
    expect(screen.getByLabelText("Order results by")).toBeInTheDocument();
  });

  it("renders exactly the supplied options", () => {
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Relevance" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Newest" })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("never renders an option the caller did not supply", () => {
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} />);
    expect(screen.queryByRole("option", { name: /most.?downloaded/i })).not.toBeInTheDocument();
  });

  it("calls onChange with the selected value", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SortSelect options={OPTIONS} value="relevance" onChange={onChange} />);

    await user.selectOptions(screen.getByRole("combobox"), "newest");

    expect(onChange).toHaveBeenCalledWith("newest");
  });

  it("disables the select when no options are supplied", () => {
    render(<SortSelect options={[]} value={null} onChange={vi.fn()} />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SortSelect options={OPTIONS} value="relevance" onChange={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
