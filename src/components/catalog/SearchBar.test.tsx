import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchBar } from "./SearchBar";

// FVS-013-IMPLEMENTATION-PLAN.md T04 — accessible presentational search
// bar. Does not call the suggestions endpoint and does not choose a
// production debounce interval or minimum character count — both are
// NEEDS BACKEND/PRODUCT CONFIRMATION (plan §1). Suggestion labels always
// render as text, never dangerouslySetInnerHTML.

describe("SearchBar", () => {
  it("renders an accessible search input", () => {
    render(<SearchBar value="" onChange={vi.fn()} />);
    expect(screen.getByRole("searchbox", { name: /search/i })).toBeInTheDocument();
  });

  it("calls onChange as the user types", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchBar value="" onChange={onChange} />);

    await user.type(screen.getByRole("searchbox"), "a");

    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("shows a Clear button when there is text, and it resets the value", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchBar value="printer" onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /clear/i }));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("hides the Clear button when the value is empty", () => {
    render(<SearchBar value="" onChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /clear/i })).not.toBeInTheDocument();
  });

  it("calls onSubmit with the current value on form submission, without a real navigation", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<SearchBar value="printer" onChange={vi.fn()} onSubmit={onSubmit} />);

    await user.type(screen.getByRole("searchbox"), "{Enter}");

    expect(onSubmit).toHaveBeenCalledWith("printer");
  });

  it("shows a loading state while suggestions are being fetched", () => {
    render(<SearchBar value="printer" onChange={vi.fn()} isLoadingSuggestions />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows a safe empty-suggestions message when suggestions resolve to none", () => {
    render(<SearchBar value="printer" onChange={vi.fn()} suggestions={[]} />);
    expect(screen.getByText(/no suggestions/i)).toBeInTheDocument();
  });

  it("renders no suggestion UI at all when suggestions are simply not supplied", () => {
    render(<SearchBar value="printer" onChange={vi.fn()} />);
    expect(screen.queryByText(/no suggestions/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("renders suggestion labels as plain text, never interpreted HTML", () => {
    render(
      <SearchBar
        value="printer"
        onChange={vi.fn()}
        suggestions={[{ label: "<b>3D printer</b>" }]}
      />
    );
    expect(screen.getByText("<b>3D printer</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });

  it("calls onSelectSuggestion with the exact suggestion when a suggestion is chosen", async () => {
    const onSelectSuggestion = vi.fn();
    const user = userEvent.setup();
    const suggestion = { label: "3D printer" };
    render(
      <SearchBar value="printer" onChange={vi.fn()} suggestions={[suggestion]} onSelectSuggestion={onSelectSuggestion} />
    );

    await user.click(screen.getByRole("button", { name: "3D printer" }));

    expect(onSelectSuggestion).toHaveBeenCalledWith(suggestion);
  });

  it("renders suggestions as real, keyboard-reachable buttons", () => {
    render(<SearchBar value="printer" onChange={vi.fn()} suggestions={[{ label: "3D printer" }]} />);
    expect(screen.getByRole("button", { name: "3D printer" }).tagName).toBe("BUTTON");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SearchBar value="" onChange={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<SearchBar value="" onChange={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
