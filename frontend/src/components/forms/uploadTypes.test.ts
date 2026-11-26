import { describe, it, expect } from "vitest";
import { precheckFiles } from "./uploadTypes";

// FVS-012-IMPLEMENTATION-PLAN.md T01 — UX-only local precheck. No number
// or MIME type is ever hardcoded here; every limit comes from the
// caller-supplied config, and an absent field means "not locally
// enforced," never "no backend limit."

function makeFile(name: string, type: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

describe("precheckFiles", () => {
  it("accepts every file when no config limits are supplied", () => {
    const files = [makeFile("a.png", "image/png", 10), makeFile("b.exe", "application/x-msdownload", 999_999)];
    const result = precheckFiles(files, {}, 0);
    expect(result.accepted).toEqual(files);
    expect(result.rejected).toEqual([]);
  });

  it("rejects a file whose type is not in the supplied allowlist", () => {
    const file = makeFile("notes.txt", "text/plain", 10);
    const result = precheckFiles([file], { allowedMimeTypes: ["image/png", "image/jpeg"] }, 0);
    expect(result.accepted).toEqual([]);
    expect(result.rejected).toEqual([{ file, reason: expect.stringContaining("notes.txt") }]);
  });

  it("accepts a file whose type is in the supplied allowlist", () => {
    const file = makeFile("photo.png", "image/png", 10);
    const result = precheckFiles([file], { allowedMimeTypes: ["image/png"] }, 0);
    expect(result.accepted).toEqual([file]);
  });

  it("rejects a file larger than the supplied maxBytes", () => {
    const file = makeFile("big.png", "image/png", 1000);
    const result = precheckFiles([file], { maxBytes: 500 }, 0);
    expect(result.accepted).toEqual([]);
    expect(result.rejected[0]?.reason).toContain("big.png");
  });

  it("accepts a file at or under the supplied maxBytes", () => {
    const file = makeFile("ok.png", "image/png", 500);
    const result = precheckFiles([file], { maxBytes: 500 }, 0);
    expect(result.accepted).toEqual([file]);
  });

  it("rejects files beyond the supplied maxFiles, counting already-accepted files", () => {
    const first = makeFile("one.png", "image/png", 10);
    const second = makeFile("two.png", "image/png", 10);
    const result = precheckFiles([first, second], { maxFiles: 1 }, 0);
    expect(result.accepted).toEqual([first]);
    expect(result.rejected).toEqual([{ file: second, reason: expect.stringContaining("two.png") }]);
  });

  it("accounts for a nonzero currentAcceptedCount against maxFiles", () => {
    const file = makeFile("three.png", "image/png", 10);
    const result = precheckFiles([file], { maxFiles: 2 }, 2);
    expect(result.accepted).toEqual([]);
    expect(result.rejected).toEqual([{ file, reason: expect.stringContaining("three.png") }]);
  });
});
