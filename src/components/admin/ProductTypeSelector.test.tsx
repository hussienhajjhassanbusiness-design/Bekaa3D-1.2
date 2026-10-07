import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductTypeSelector } from "./ProductTypeSelector";

// FVS-011-IMPLEMENTATION-PLAN.md T02 — a normalized presentational
// selector only. "physical"/"stl" are internal frontend UI literals
// (#FVS011-PRODUCT-TYPE), never a claim about the backend's actual
// discriminator field name or enum strings — both are still NEEDS
// BACKEND CONFIRMATION (plan §1). Product type is immutable after
// creation (vertical-slice-plan.md VS-011's own Logic line): edit mode
// locks the selector and explains why via aria-describedby, not a bare
// grayed-out look.

describe("ProductTypeSelector", () => {
  it("offers exactly the two known product type choices", () => {
    render(<ProductTypeSelector mode="create" value="physical" onChange={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getByRole("radio", { name: /physical/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /stl/i })).toBeInTheDocument();
  });

  it("is selectable in create mode", () => {
    render(<ProductTypeSelector mode="create" value="physical" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /physical/i })).not.toBeDisabled();
    expect(screen.getByRole("radio", { name: /stl/i })).not.toBeDisabled();
  });

  it("reflects the current value as checked", () => {
    render(<ProductTypeSelector mode="create" value="stl" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /stl/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /physical/i })).not.toBeChecked();
  });

  it("calls onChange with the internal literal when a different option is chosen", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ProductTypeSelector mode="create" value="physical" onChange={onChange} />);

    await user.click(screen.getByRole("radio", { name: /stl/i }));

    expect(onChange).toHaveBeenCalledWith("stl");
  });

  it("locks both options in edit mode", () => {
    render(<ProductTypeSelector mode="edit" value="physical" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /physical/i })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /stl/i })).toBeDisabled();
  });

  it("never calls onChange when a locked option is clicked in edit mode", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ProductTypeSelector mode="edit" value="physical" onChange={onChange} />);

    await user.click(screen.getByRole("radio", { name: /stl/i }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it("associates a visible lock explanation via aria-describedby in edit mode", () => {
    render(<ProductTypeSelector mode="edit" value="physical" onChange={vi.fn()} />);
    const group = screen.getByRole("radiogroup");
    const describedById = group.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    const explanation = document.getElementById(describedById!);
    expect(explanation).not.toBeNull();
    expect(explanation?.textContent).toMatch(/can.?t be changed/i);
  });

  it("does not render a lock explanation in create mode", () => {
    render(<ProductTypeSelector mode="create" value="physical" onChange={vi.fn()} />);
    expect(screen.queryByText(/can.?t be changed/i)).not.toBeInTheDocument();
  });

  it("is reachable by keyboard (Tab) even though it is a native radio group", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <button type="button">before</button>
        <ProductTypeSelector mode="create" value="physical" onChange={vi.fn()} />
      </div>
    );

    await user.tab();
    await user.tab();

    expect(screen.getByRole("radio", { name: /physical/i })).toHaveFocus();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<ProductTypeSelector mode="create" value="physical" onChange={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
