import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import { useSearchSuggestions } from "./useSearchSuggestions";

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useSearchSuggestions", () => {
  it("never calls the API below the 3-character minimum — no request sent, not even a disabled-state fetch", async () => {
    vi.useFakeTimers();
    const getSpy = vi.spyOn(apiClient, "get");

    const { result } = renderHook(() => useSearchSuggestions("dr"), { wrapper: createWrapper() });
    await vi.advanceTimersByTimeAsync(1000);

    expect(result.current.isQueryLongEnough).toBe(false);
    expect(getSpy).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("debounces: does not call the API before ~300ms have passed since the last keystroke", async () => {
    vi.useFakeTimers();
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [] });

    const { rerender } = renderHook(({ q }) => useSearchSuggestions(q), {
      wrapper: createWrapper(),
      initialProps: { q: "dr" },
    });
    rerender({ q: "dra" });
    await vi.advanceTimersByTimeAsync(299);

    expect(getSpy).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("calls the API once settled past the debounce window with the trimmed query", async () => {
    vi.useFakeTimers();
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({
      items: [{ id: "p1", name: "Articulated Dragon", slug: "dragon", type: "physical" }],
    });

    const { result } = renderHook(() => useSearchSuggestions("  dragon  "), { wrapper: createWrapper() });
    await vi.advanceTimersByTimeAsync(300);

    expect(getSpy).toHaveBeenCalledWith("/api/v1/search/suggestions?q=dragon");
    expect(result.current.data).toEqual([{ id: "p1", name: "Articulated Dragon", slug: "dragon", type: "physical" }]);
    vi.useRealTimers();
  });

  it("a stale response for an earlier term never overwrites the result for the current term", async () => {
    vi.useFakeTimers();
    let resolveFirst!: (value: unknown) => void;
    vi.spyOn(apiClient, "get").mockImplementation((path: unknown) => {
      const pathStr = path as string;
      if (pathStr.includes("q=drag")) {
        return new Promise((resolve) => {
          resolveFirst = resolve;
        });
      }
      return Promise.resolve({
        items: [{ id: "p2", name: "Articulated Knight", slug: "knight", type: "physical" }],
      });
    });

    const { result, rerender } = renderHook(({ q }) => useSearchSuggestions(q), {
      wrapper: createWrapper(),
      initialProps: { q: "drag" },
    });
    await vi.advanceTimersByTimeAsync(300);

    rerender({ q: "knig" });
    await vi.advanceTimersByTimeAsync(300);
    for (let i = 0; i < 5; i++) {
      await vi.advanceTimersByTimeAsync(0);
    }

    expect(result.current.data).toEqual([
      { id: "p2", name: "Articulated Knight", slug: "knight", type: "physical" },
    ]);

    // The first ("drag") request now resolves late — it must never replace
    // the already-rendered "knig" result, since the hook always reads the
    // cache entry for the CURRENT debounced term.
    resolveFirst({ items: [{ id: "p1", name: "Articulated Dragon", slug: "dragon", type: "physical" }] });
    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.data).toEqual([
      { id: "p2", name: "Articulated Knight", slug: "knight", type: "physical" },
    ]);
    vi.useRealTimers();
  });
});
