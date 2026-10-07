import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useScanStatusPolling } from "./useScanStatusPolling";
import type { AssetFile } from "./assetVersionWorkflow";

// FVS-018-IMPLEMENTATION-PLAN.md T05 — #ARCHITECTURE-SCAN-POLLING.
// Contract-independent: `intervalMs` is a REQUIRED input, never a
// built-in production default — "scan should be done by now" is never
// inferred from elapsed client time; this hook only decides WHETHER to
// poll (any file still "pending") and lets the caller's own `onPoll`
// decide what polling actually does (a future TanStack refetch, not
// this hook's concern). No WebSocket/SSE — polling only, per VS-016's
// own "no push mechanism" confirmation.

function pendingFile(id = "f-1"): AssetFile {
  return { id, displayName: `${id}.stl`, scanStatus: "pending" };
}
function cleanFile(id = "f-1"): AssetFile {
  return { id, displayName: `${id}.stl`, scanStatus: "clean" };
}
function infectedFile(id = "f-1"): AssetFile {
  return { id, displayName: `${id}.stl`, scanStatus: "infected" };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useScanStatusPolling", () => {
  it("polls at the supplied interval while a file is pending", () => {
    const onPoll = vi.fn();
    renderHook(() => useScanStatusPolling({ files: [pendingFile()], intervalMs: 5000, onPoll }));

    vi.advanceTimersByTime(5000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(5000);
    expect(onPoll).toHaveBeenCalledTimes(2);
  });

  it("uses exactly the supplied interval, never a different built-in one", () => {
    const onPoll = vi.fn();
    renderHook(() => useScanStatusPolling({ files: [pendingFile()], intervalMs: 1000, onPoll }));

    vi.advanceTimersByTime(999);
    expect(onPoll).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(onPoll).toHaveBeenCalledTimes(1);
  });

  it("does not poll at all when the initial state is already terminal (all clean)", () => {
    const onPoll = vi.fn();
    renderHook(() => useScanStatusPolling({ files: [cleanFile()], intervalMs: 1000, onPoll }));

    vi.advanceTimersByTime(10_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("does not poll at all when the initial state is terminal (clean + infected, no pending)", () => {
    const onPoll = vi.fn();
    renderHook(() =>
      useScanStatusPolling({ files: [cleanFile("a"), infectedFile("b")], intervalMs: 1000, onPoll })
    );

    vi.advanceTimersByTime(10_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("stops polling once a rerender reports all files resolved to clean", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ files }: { files: readonly AssetFile[] }) => useScanStatusPolling({ files, intervalMs: 1000, onPoll }),
      { initialProps: { files: [pendingFile()] } }
    );

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    rerender({ files: [cleanFile()] });
    onPoll.mockClear();
    vi.advanceTimersByTime(10_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("stops polling once a rerender reports a terminal clean+infected mix", () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ files }: { files: readonly AssetFile[] }) => useScanStatusPolling({ files, intervalMs: 1000, onPoll }),
      { initialProps: { files: [pendingFile("a"), cleanFile("b")] } }
    );

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    rerender({ files: [infectedFile("a"), cleanFile("b")] });
    onPoll.mockClear();
    vi.advanceTimersByTime(10_000);
    expect(onPoll).not.toHaveBeenCalled();
  });

  it("stops polling on unmount", () => {
    const onPoll = vi.fn();
    const { unmount } = renderHook(() => useScanStatusPolling({ files: [pendingFile()], intervalMs: 1000, onPoll }));

    vi.advanceTimersByTime(1000);
    expect(onPoll).toHaveBeenCalledTimes(1);

    unmount();
    onPoll.mockClear();
    vi.advanceTimersByTime(10_000);
    expect(onPoll).not.toHaveBeenCalled();
  });
});
