import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecoveryCodeList } from "./RecoveryCodeList";

// FVS-005-IMPLEMENTATION-PLAN.md T01 (CAN IMPLEMENT NOW — contract-
// independent) — presentation-only. This component never fetches, never
// regenerates, and owns no API/business state; it only safely presents
// recovery codes supplied by its parent through props. No backend
// response-object type is assumed anywhere in these tests.

const CODES = ["aaaa-bbbb", "cccc-dddd", "eeee-ffff"] as const;

function mockClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
}

// @testing-library/user-event's setup() installs its own navigator.clipboard
// stub as a side effect — calling it AFTER mockClipboard() silently
// discards our override. Every test that needs both must call setup()
// first, then apply its own clipboard mock.
function setupUserWithClipboard(writeText: (text: string) => Promise<void>) {
  const user = userEvent.setup();
  mockClipboard(writeText);
  return user;
}

describe("RecoveryCodeList", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders each supplied code exactly", () => {
    render(<RecoveryCodeList codes={CODES} />);
    for (const code of CODES) {
      expect(screen.getByText(code)).toBeInTheDocument();
    }
  });

  it("preserves spaces and punctuation in a code exactly, with no trimming", () => {
    render(<RecoveryCodeList codes={["  a.b-c_d  "]} />);
    expect(screen.getByText("a.b-c_d", { exact: false }).textContent).toBe("  a.b-c_d  ");
  });

  it("uses semantic list markup", () => {
    render(<RecoveryCodeList codes={CODES} />);
    const list = screen.getByRole("list");
    expect(list.tagName).toBe("UL");
    expect(screen.getAllByRole("listitem")).toHaveLength(CODES.length);
  });

  it("renders codes as real, selectable text — never as an image or canvas", () => {
    render(<RecoveryCodeList codes={CODES} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(document.querySelector("canvas")).toBeNull();
    expect(screen.getByText(CODES[0]).textContent).toBe(CODES[0]);
  });

  it("the copy action is a real, keyboard-operable button", () => {
    render(<RecoveryCodeList codes={CODES} />);
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("never calls the clipboard until the user actually clicks copy", () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);
    render(<RecoveryCodeList codes={CODES} />);
    expect(writeText).not.toHaveBeenCalled();
  });

  it("copies one exact code per line, in order, when the user clicks copy", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const user = setupUserWithClipboard(writeText);
    render(<RecoveryCodeList codes={CODES} />);

    await user.click(screen.getByRole("button", { name: /copy/i }));

    expect(writeText).toHaveBeenCalledWith(CODES.join("\n"));
  });

  it("does not trim or normalize codes when copying", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const user = setupUserWithClipboard(writeText);
    render(<RecoveryCodeList codes={["  spaced  ", "UPPER-lower"]} />);

    await user.click(screen.getByRole("button", { name: /copy/i }));

    expect(writeText).toHaveBeenCalledWith("  spaced  \nUPPER-lower");
  });

  it("shows accessible feedback after a successful copy", async () => {
    const user = setupUserWithClipboard(vi.fn().mockResolvedValue(undefined));
    render(<RecoveryCodeList codes={CODES} />);

    await user.click(screen.getByRole("button", { name: /copy/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/copied/i);
  });

  it("shows safe accessible feedback when the clipboard rejects, never the raw error", async () => {
    const user = setupUserWithClipboard(
      vi.fn().mockRejectedValue(new Error("NotAllowedError: raw-browser-internal-detail"))
    );
    render(<RecoveryCodeList codes={CODES} />);

    await user.click(screen.getByRole("button", { name: /copy/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toContain("raw-browser-internal-detail");
    expect(alert.textContent).not.toContain("NotAllowedError");
  });

  it("the print action only calls window.print after the user clicks it", async () => {
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<RecoveryCodeList codes={CODES} />);

    expect(printSpy).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /print/i }));
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it("does not fabricate sample codes when given an empty array", () => {
    render(<RecoveryCodeList codes={[]} />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /copy/i })).not.toBeInTheDocument();
  });

  it("never writes to localStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<RecoveryCodeList codes={CODES} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("never writes to sessionStorage", () => {
    const spy = vi.spyOn(window.sessionStorage.__proto__, "setItem");
    render(<RecoveryCodeList codes={CODES} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("never writes document.cookie", () => {
    const before = document.cookie;
    render(<RecoveryCodeList codes={CODES} />);
    expect(document.cookie).toBe(before);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<RecoveryCodeList codes={CODES} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never logs to the console", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = setupUserWithClipboard(vi.fn().mockResolvedValue(undefined));
    render(<RecoveryCodeList codes={CODES} />);
    await user.click(screen.getByRole("button", { name: /copy/i }));
    expect(logSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it("leaves no stale reference to a previous mount's codes after unmount", () => {
    const { unmount } = render(<RecoveryCodeList codes={["first-batch-code"]} />);
    unmount();

    render(<RecoveryCodeList codes={["second-batch-code"]} />);
    expect(screen.queryByText("first-batch-code")).not.toBeInTheDocument();
    expect(screen.getByText("second-batch-code")).toBeInTheDocument();
  });

  it("includes clear warning copy about saving and sensitivity, without inventing backend-specific regeneration/invalidation detail", () => {
    render(<RecoveryCodeList codes={CODES} />);
    expect(screen.getByText(/save these codes now/i)).toBeInTheDocument();
    expect(screen.getByText(/may not be shown again/i)).toBeInTheDocument();
  });
});
