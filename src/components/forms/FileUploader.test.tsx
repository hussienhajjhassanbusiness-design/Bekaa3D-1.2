import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileUploader } from "./FileUploader";
import type { UploadDriver, UploadDriverHandlers, UploadDriverResult } from "./FileUploader";

// FVS-012-IMPLEMENTATION-PLAN.md T02 — shared, product-agnostic upload
// UX. Transport is an injected `UploadDriver` seam (T03 absorbed here —
// see the plan's own recorded decision): no real HTTP, no XHR/fetch, no
// multipart implementation in this component. A future endpoint-specific
// adapter (product images, STL assets, BYI attachments) supplies the
// real driver once its contract is confirmed.

function makeFile(name: string, type: string, sizeBytes = 10): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

function resolvingDriver(result: UploadDriverResult, progressSteps: number[] = [50, 100]): UploadDriver {
  return vi.fn((_file: File, handlers: UploadDriverHandlers) => {
    progressSteps.forEach((p) => handlers.onProgress(p));
    return Promise.resolve(result);
  });
}

function rejectingDriver(error: unknown): UploadDriver {
  return vi.fn(() => Promise.reject(error));
}

function hangingDriver(): { driver: UploadDriver; abortedSignals: AbortSignal[] } {
  const abortedSignals: AbortSignal[] = [];
  const driver: UploadDriver = vi.fn((_file: File, handlers: UploadDriverHandlers) => {
    return new Promise<UploadDriverResult>((_resolve, reject) => {
      handlers.signal.addEventListener("abort", () => {
        abortedSignals.push(handlers.signal);
        reject(new DOMException("Aborted", "AbortError"));
      });
    });
  });
  return { driver, abortedSignals };
}

describe("FileUploader", () => {
  it("renders a real native file input", () => {
    render(<FileUploader label="Upload images" config={{}} driver={resolvingDriver({ ok: true })} />);
    const input = screen.getByLabelText("Upload images");
    expect(input).toHaveAttribute("type", "file");
  });

  it("supports multiple file selection when configured", () => {
    render(<FileUploader label="Upload images" config={{}} driver={resolvingDriver({ ok: true })} multiple />);
    expect(screen.getByLabelText("Upload images")).toHaveAttribute("multiple");
  });

  it("accepts a file dropped onto the dropzone", async () => {
    const driver = resolvingDriver({ ok: true });
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const file = makeFile("photo.png", "image/png");

    const dropzone = screen.getByTestId("file-dropzone");
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });

    expect(await screen.findByText("photo.png")).toBeInTheDocument();
  });

  it("accepts a file chosen through the native picker", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const file = makeFile("photo.png", "image/png");

    await user.upload(screen.getByLabelText("Upload images"), file);

    expect(screen.getByText("photo.png")).toBeInTheDocument();
  });

  it("passes the exact selected File object to the driver", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const file = makeFile("photo.png", "image/png");

    await user.upload(screen.getByLabelText("Upload images"), file);

    expect(driver).toHaveBeenCalledWith(file, expect.anything());
  });

  it("rejects a disallowed MIME type locally and never calls the driver", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{ allowedMimeTypes: ["image/png"] }} driver={driver} />);
    const file = makeFile("notes.txt", "text/plain");

    await user.upload(screen.getByLabelText("Upload images"), file);

    expect(driver).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("notes.txt");
  });

  it("rejects an oversized file locally and never calls the driver", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{ maxBytes: 5 }} driver={driver} />);
    const file = makeFile("big.png", "image/png", 100);

    await user.upload(screen.getByLabelText("Upload images"), file);

    expect(driver).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("big.png");
  });

  it("enforces a supplied maxFiles limit", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{ maxFiles: 1 }} driver={driver} multiple />);
    const files = [makeFile("one.png", "image/png"), makeFile("two.png", "image/png")];

    await user.upload(screen.getByLabelText("Upload images"), files);

    expect(driver).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent("two.png");
  });

  it("imposes no hardcoded size limit when none is configured", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const hugeFile = makeFile("huge.png", "image/png", 50_000_000);

    await user.upload(screen.getByLabelText("Upload images"), hugeFile);

    expect(driver).toHaveBeenCalledWith(hugeFile, expect.anything());
  });

  it("imposes no hardcoded MIME allowlist when none is configured", async () => {
    const driver = resolvingDriver({ ok: true });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const anyFile = makeFile("archive.zip", "application/zip");

    await user.upload(screen.getByLabelText("Upload images"), anyFile);

    expect(driver).toHaveBeenCalledWith(anyFile, expect.anything());
  });

  it("shows a progress indicator for an in-flight upload", async () => {
    const { driver } = hangingDriver();
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("exposes accessible progress semantics via a native <progress> element", async () => {
    const { driver } = hangingDriver();
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    const progress = screen.getByRole("progressbar");
    expect(progress.tagName).toBe("PROGRESS");
  });

  it("provides an aria-live polite status region", () => {
    render(<FileUploader label="Upload images" config={{}} driver={resolvingDriver({ ok: true })} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("does not claim success while bytes have reached 100% but the driver has not resolved", async () => {
    const { driver } = hangingDriver();
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    expect(screen.queryByText(/uploaded/i)).not.toBeInTheDocument();
  });

  it("cancel aborts the in-flight request via the driver's signal", async () => {
    const { driver, abortedSignals } = hangingDriver();
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(abortedSignals).toHaveLength(1);
  });

  it("retry re-invokes the driver with the same File object", async () => {
    const driver = resolvingDriver({ ok: false, reason: "Server rejected this file." });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);
    const file = makeFile("photo.png", "image/png");

    await user.upload(screen.getByLabelText("Upload images"), file);
    await screen.findByRole("button", { name: /retry/i });
    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(driver).toHaveBeenCalledTimes(2);
    expect(driver).toHaveBeenNthCalledWith(1, file, expect.anything());
    expect(driver).toHaveBeenNthCalledWith(2, file, expect.anything());
  });

  it("shows the driver's specific rejection reason, not a generic message", async () => {
    const driver = resolvingDriver({ ok: false, reason: "Malware scan rejected this file." });
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    expect(await screen.findByText("Malware scan rejected this file.")).toBeInTheDocument();
  });

  it("never renders a raw exception/debug object when the driver throws", async () => {
    const driver = rejectingDriver(new Error("ECONNRESET at internal/stream.js:412 stack trace garbage"));
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={driver} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    await screen.findByRole("button", { name: /retry/i });
    expect(screen.queryByText(/ECONNRESET/)).not.toBeInTheDocument();
    expect(screen.queryByText(/stack trace/)).not.toBeInTheDocument();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={resolvingDriver({ ok: true })} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    expect(spy).not.toHaveBeenCalled();
  });

  it("never makes a real network/fetch call itself", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    render(<FileUploader label="Upload images" config={{}} driver={resolvingDriver({ ok: true })} />);

    await user.upload(screen.getByLabelText("Upload images"), makeFile("photo.png", "image/png"));

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
