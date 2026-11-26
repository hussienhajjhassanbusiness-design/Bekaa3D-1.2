import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoadMore } from "./LoadMore";

// FVS-013-IMPLEMENTATION-PLAN.md T06 — cursor pagination means no
// numbered page picker; this component never interprets or constructs a
// cursor itself, only exposes a presentational "Load more" seam.
// `hasMore` is entirely parent-controlled.

describe("LoadMore", () => {
  it("renders a Load more button when hasMore is true", () => {
    render(<LoadMore hasMore onLoadMore={vi.fn()} />);
    expect(screen.getByRole("button", { name: /load more/i })).toBeInTheDocument();
  });

  it("renders nothing when hasMore is false", () => {
    render(<LoadMore hasMore={false} onLoadMore={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onLoadMore when activated", async () => {
    const onLoadMore = vi.fn();
    const user = userEvent.setup();
    render(<LoadMore hasMore onLoadMore={onLoadMore} />);

    await user.click(screen.getByRole("button", { name: /load more/i }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("disables the button while loading", () => {
    render(<LoadMore hasMore onLoadMore={vi.fn()} isLoading />);
    expect(screen.getByRole("button", { name: /load more/i })).toBeDisabled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<LoadMore hasMore onLoadMore={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
