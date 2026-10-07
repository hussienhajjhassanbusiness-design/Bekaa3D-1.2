import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DownloadButton } from "./DownloadButton";

// FVS-021-IMPLEMENTATION-PLAN.md T01 — #ARCHITECTURE-NATIVE-STL-DOWNLOAD.
// This MUST be a real <a> — the backend streams through nginx
// X-Accel-Redirect and supports HTTP Range; a fetch→Blob→
// createObjectURL path would silently break resume/range support for
// large files. Future contributors must NOT refactor this into a JS
// download handler. #SECURITY-AUTHORIZED-DOWNLOAD-HREF: the component
// accepts only an already-authorized href from a future adapter — it
// never derives one from storage metadata itself.

describe("DownloadButton", () => {
  it("renders a real anchor element", () => {
    render(<DownloadButton authorizedHref="/api/v1/me/downloads/ent-1" accessibleLabel="Download Dragon STL" />);
    expect(screen.getByRole("link").tagName).toBe("A");
  });

  it("preserves the exact supplied href, never deriving or rewriting it", () => {
    render(<DownloadButton authorizedHref="/api/v1/me/downloads/ent-1" accessibleLabel="Download Dragon STL" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/api/v1/me/downloads/ent-1");
  });

  it("uses the exact supplied accessible label, including file/product context, never a bare 'Download'", () => {
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(screen.getByRole("link", { name: "Download Dragon STL" })).toBeInTheDocument();
  });

  it("is not a button pretending to be a link", () => {
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not add a client-specified download filename — backend Content-Disposition stays authoritative", () => {
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(screen.getByRole("link")).not.toHaveAttribute("download");
  });

  it("does not open in a new tab by default", () => {
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(screen.getByRole("link")).not.toHaveAttribute("target");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never calls URL.createObjectURL", () => {
    // jsdom does not implement createObjectURL by default — install a
    // temporary mock rather than assuming it exists to spy on.
    const original = (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    const mockCreateObjectURL = vi.fn();
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = mockCreateObjectURL;

    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);

    expect(mockCreateObjectURL).not.toHaveBeenCalled();
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = original;
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<DownloadButton authorizedHref="/x" accessibleLabel="Download Dragon STL" />);
    expect(spy).not.toHaveBeenCalled();
  });
});
