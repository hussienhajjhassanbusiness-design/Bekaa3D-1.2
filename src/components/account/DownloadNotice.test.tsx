import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DownloadNotice } from "./DownloadNotice";

// FVS-021-IMPLEMENTATION-PLAN.md T04 — safe presentational notices
// only. No backend status code is mapped here (that is a future
// adapter's job) and no reset time is ever calculated client-side —
// `resetTimeLabel` is an optional, already-safe string a future
// adapter supplies verbatim once Retry-After semantics are confirmed.
// Critically, this component is never wired to a pre-flight fetch —
// the native anchor download architecture stays authoritative; these
// notices are rendered from state a parent already has (e.g. a prior
// failed navigation signal), never from a check-before-click request
// this component itself triggers.

describe("DownloadNotice", () => {
  it("shows general cap guidance when no reset time is supplied", () => {
    render(<DownloadNotice kind="cap" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/download limit/i);
  });

  it("includes a supplied reset time verbatim, without calculating one itself", () => {
    render(<DownloadNotice kind="cap" resetTimeLabel="at midnight UTC" />);
    expect(screen.getByRole("alert")).toHaveTextContent("at midnight UTC");
  });

  it("shows a revoked/no-longer-entitled message", () => {
    render(<DownloadNotice kind="revoked" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/no longer available/i);
  });

  it("shows a safe generic message for an unclassified failure", () => {
    render(<DownloadNotice kind="generic" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DownloadNotice kind="cap" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
