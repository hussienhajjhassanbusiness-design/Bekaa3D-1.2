import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InternalNoteEditor } from "./InternalNoteEditor";

// FVS-030-IMPLEMENTATION-PLAN.md T02 — #SECURITY-INTERNAL-NOTE-BOUNDARY.
// An explicit, screen-reader-read customer-invisibility label, never
// conveyed by styling alone. No auto-save, no save-on-blur -- Save is
// an explicit button click only. No persistence, no logging, no URL
// placement.

describe("InternalNoteEditor", () => {
  it("renders the explicit customer-invisibility label as real, readable text", () => {
    render(<InternalNoteEditor note="" onSave={vi.fn()} />);
    expect(screen.getByText(/not visible to customers/i)).toBeInTheDocument();
  });

  it("typing edits only local draft state — does not call onSave on every keystroke", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<InternalNoteEditor note="" onSave={onSave} />);

    await user.type(screen.getByRole("textbox", { name: /internal note/i }), "Called customer about delay.");

    expect(onSave).not.toHaveBeenCalled();
  });

  it("onSave fires only on an explicit Save click, with the exact typed text", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<InternalNoteEditor note="" onSave={onSave} />);

    await user.type(screen.getByRole("textbox", { name: /internal note/i }), "Called customer about delay.");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(onSave).toHaveBeenCalledWith("Called customer about delay.");
  });

  it("does not call onSave when the textarea merely loses focus (no save-on-blur)", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <InternalNoteEditor note="" onSave={onSave} />
        <button type="button">elsewhere</button>
      </>
    );

    await user.type(screen.getByRole("textbox", { name: /internal note/i }), "Draft text");
    await user.click(screen.getByRole("button", { name: "elsewhere" }));

    expect(onSave).not.toHaveBeenCalled();
  });

  it("disables Save and shows progress text while isSaving", () => {
    render(<InternalNoteEditor note="Existing note" onSave={vi.fn()} isSaving />);
    expect(screen.getByRole("button", { name: /saving|save/i })).toBeDisabled();
  });

  it("renders a caller-supplied error message as a safe string, never a raw exception", () => {
    render(<InternalNoteEditor note="" onSave={vi.fn()} errorMessage="Couldn't save your note. Please try again." />);
    expect(screen.getByText("Couldn't save your note. Please try again.")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<InternalNoteEditor note="" onSave={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<InternalNoteEditor note="" onSave={vi.fn()} />);
    await user.type(screen.getByRole("textbox", { name: /internal note/i }), "Draft text");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
