import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCursorPagination } from "./useCursorPagination";

// Phase 3 — every admin list (settings, users, categories, materials,
// colours, products) is cursor-paginated (C2: {items, next_cursor},
// never a page number). AdminTable already exposes controlled
// hasPrevious/hasNext/onPrevious/onNext props; this hook supplies them
// by keeping a client-side stack of visited cursors — "Previous" pops
// the stack, "Next" pushes the server's own next_cursor. There is no
// backend "go back" cursor, so this stack is the only way to support a
// Previous button at all.
describe("useCursorPagination", () => {
  it("starts with cursor undefined (first page) and hasPrevious false", () => {
    const { result } = renderHook(() => useCursorPagination());

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrevious).toBe(false);
  });

  it("advances to the given cursor on goNext and reports hasPrevious true", () => {
    const { result } = renderHook(() => useCursorPagination());

    act(() => {
      result.current.goNext("cursor-page-2");
    });

    expect(result.current.cursor).toBe("cursor-page-2");
    expect(result.current.hasPrevious).toBe(true);
  });

  it("pops back to the prior cursor on goPrevious", () => {
    const { result } = renderHook(() => useCursorPagination());

    act(() => {
      result.current.goNext("cursor-page-2");
    });
    act(() => {
      result.current.goNext("cursor-page-3");
    });
    act(() => {
      result.current.goPrevious();
    });

    expect(result.current.cursor).toBe("cursor-page-2");
    expect(result.current.hasPrevious).toBe(true);
  });

  it("goPrevious on the first page is a no-op", () => {
    const { result } = renderHook(() => useCursorPagination());

    act(() => {
      result.current.goPrevious();
    });

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrevious).toBe(false);
  });

  it("resets to the first page when resetKey changes", () => {
    const { result, rerender } = renderHook(({ resetKey }) => useCursorPagination(resetKey), {
      initialProps: { resetKey: "a" },
    });

    act(() => {
      result.current.goNext("cursor-page-2");
    });
    expect(result.current.cursor).toBe("cursor-page-2");

    rerender({ resetKey: "b" });

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrevious).toBe(false);
  });

  it("does not reset when rerendered with the same resetKey", () => {
    const { result, rerender } = renderHook(({ resetKey }) => useCursorPagination(resetKey), {
      initialProps: { resetKey: "a" },
    });

    act(() => {
      result.current.goNext("cursor-page-2");
    });
    rerender({ resetKey: "a" });

    expect(result.current.cursor).toBe("cursor-page-2");
  });
});
