import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetVersionUploader } from "./AssetVersionUploader";

// FVS-018-IMPLEMENTATION-PLAN.md T04 — reuses the shared FileUploader
// (FVS-012) directly in its deferred-selection mode, since the real
// bundle-create endpoint/body is unconfirmed (no driver is passed, so
// nothing uploads per-file). Not a second picker/dropzone/precheck
// implementation. No MIME/size/count limit is hardcoded here — VS-016
// never confirms allowed bundle formats, and ".stl"/".zip"/"3mf" must
// not be inferred from the slice's own name.

function makeFile(name: string, type = "application/octet-stream", sizeBytes = 10): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

describe("AssetVersionUploader", () => {
  it("reuses the shared FileUploader dropzone, not a duplicated picker", () => {
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    expect(screen.getByTestId("file-dropzone")).toBeInTheDocument();
  });

  it("renders a real native file input supporting multiple files", () => {
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    const input = screen.getByLabelText(/asset version/i);
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("multiple");
  });

  it("reports selected files to the parent without uploading them", async () => {
    const onSelectionChange = vi.fn();
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{}} onSelectionChange={onSelectionChange} />);
    const file = makeFile("model.stl");

    await user.upload(screen.getByLabelText(/asset version/i), file);

    expect(onSelectionChange).toHaveBeenLastCalledWith([file]);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText(/uploaded/i)).not.toBeInTheDocument();
  });

  it("imposes no hardcoded file-type limit when none is configured", async () => {
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    const file = makeFile("bundle.zip", "application/zip");

    await user.upload(screen.getByLabelText(/asset version/i), file);

    expect(screen.getByText("bundle.zip")).toBeInTheDocument();
  });

  it("imposes no hardcoded size limit when none is configured", async () => {
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    const hugeFile = makeFile("huge.stl", "application/octet-stream", 50_000_000);

    await user.upload(screen.getByLabelText(/asset version/i), hugeFile);

    expect(screen.getByText("huge.stl")).toBeInTheDocument();
  });

  it("applies a supplied precheck config (e.g. max file count)", async () => {
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{ maxFiles: 1 }} onSelectionChange={vi.fn()} />);
    const files = [makeFile("one.stl"), makeFile("two.stl")];

    await user.upload(screen.getByLabelText(/asset version/i), files);

    expect(screen.getByText("one.stl")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("two.stl");
  });

  it("never makes a network/fetch call", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    await user.upload(screen.getByLabelText(/asset version/i), makeFile("model.stl"));
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<AssetVersionUploader config={{}} onSelectionChange={vi.fn()} />);
    await user.upload(screen.getByLabelText(/asset version/i), makeFile("model.stl"));
    expect(spy).not.toHaveBeenCalled();
  });
});
