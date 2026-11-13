import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MoneyInput, parseDecimalToCents } from "./MoneyInput";

// FVS-011-IMPLEMENTATION-PLAN.md T01 — cents-safe money input. Domain
// value is always integer cents; the parser is string-based (never
// `price * 100` on a float) specifically to avoid float artifacts like
// 0.10 -> 9 or 11 cents. Rounding for >2-decimal input is NOT invented —
// vertical-slice-plan.md only says "money validation" and
// FRONTEND-VERTICAL-SLICE-PLAN.md only says "cents rounding" in a test
// summary, neither defines an actual rounding rule — so >2-decimal input
// is rejected with an explicit message instead of silently rounded
// (plan §0/§5's own recorded discrepancy).

describe("parseDecimalToCents", () => {
  it("parses a whole number", () => {
    expect(parseDecimalToCents("12")).toEqual({ ok: true, cents: 1200 });
  });

  it("parses one decimal digit", () => {
    expect(parseDecimalToCents("12.3")).toEqual({ ok: true, cents: 1230 });
  });

  it("parses two decimal digits exactly", () => {
    expect(parseDecimalToCents("12.34")).toEqual({ ok: true, cents: 1234 });
  });

  it("has no floating-point artifact for 0.10", () => {
    const result = parseDecimalToCents("0.10");
    expect(result).toEqual({ ok: true, cents: 10 });
  });

  it("rejects a negative amount rather than clamping it", () => {
    expect(parseDecimalToCents("-5")).toEqual({ ok: false, reason: "negative" });
  });

  it("rejects more than 2 decimal digits rather than rounding", () => {
    expect(parseDecimalToCents("12.345")).toEqual({ ok: false, reason: "too-many-decimals" });
  });

  it("rejects an empty string", () => {
    expect(parseDecimalToCents("")).toEqual({ ok: false, reason: "invalid" });
  });

  it("rejects a non-numeric string", () => {
    expect(parseDecimalToCents("abc")).toEqual({ ok: false, reason: "invalid" });
  });

  it("trims leading/trailing whitespace before parsing", () => {
    expect(parseDecimalToCents("  12.50  ")).toEqual({ ok: true, cents: 1250 });
  });
});

describe("MoneyInput", () => {
  it("renders with an accessible label that includes the currency unit", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} />);
    expect(screen.getByLabelText("Price (USD)")).toBeInTheDocument();
  });

  it("makes currency information programmatically available, not placeholder-only", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} />);
    const input = screen.getByLabelText("Price (USD)");
    expect(input).not.toHaveAttribute("placeholder", expect.stringContaining("USD"));
  });

  it("displays integer cents as a formatted decimal", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={1200} onChangeCents={vi.fn()} />);
    expect(screen.getByLabelText("Price (USD)")).toHaveValue("12.00");
  });

  it("maps an exact whole-unit entry to cents", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "12");

    expect(onChangeCents).toHaveBeenLastCalledWith(1200);
  });

  it("maps a one-decimal entry correctly", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "12.3");

    expect(onChangeCents).toHaveBeenLastCalledWith(1230);
  });

  it("maps a two-decimal entry exactly", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "12.34");

    expect(onChangeCents).toHaveBeenLastCalledWith(1234);
  });

  it("produces no floating-point artifact for 0.10", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "0.10");

    expect(onChangeCents).toHaveBeenLastCalledWith(10);
  });

  it("rejects a negative entry instead of emitting a clamped value", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "-5");

    expect(onChangeCents).not.toHaveBeenCalled();
  });

  it("surfaces the negative rejection accessibly", async () => {
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={vi.fn()} />);

    await user.type(screen.getByLabelText("Price (USD)"), "-5");

    expect(screen.getByRole("alert")).toHaveTextContent(/negative/i);
  });

  it("rejects more than 2 decimal digits instead of silently rounding", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "12.345");

    // The last valid prefix ("12.34") was emitted as the user typed it;
    // the final, too-precise keystroke must not emit anything further —
    // never a silently rounded value.
    expect(onChangeCents).toHaveBeenLastCalledWith(1234);
    expect(screen.getByRole("alert")).toHaveTextContent(/2 decimal/i);
  });

  it("clearing the field emits a null (empty) value", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={1200} onChangeCents={onChangeCents} />);

    await user.clear(screen.getByLabelText("Price (USD)"));

    expect(onChangeCents).toHaveBeenLastCalledWith(null);
  });

  it("a partial, unparseable edit does not emit a corrupted cents value", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    const input = screen.getByLabelText("Price (USD)");
    await user.type(input, "12");
    onChangeCents.mockClear();
    await user.type(input, ".");

    expect(onChangeCents).not.toHaveBeenCalled();
  });

  it("trims leading/trailing whitespace before mapping to cents", async () => {
    const onChangeCents = vi.fn();
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={onChangeCents} />);

    await user.type(screen.getByLabelText("Price (USD)"), "  12.50  ");

    expect(onChangeCents).toHaveBeenLastCalledWith(1250);
  });

  it("reflects a controlled external update to valueCents", () => {
    const { rerender } = render(<MoneyInput label="Price" currencyLabel="USD" valueCents={500} onChangeCents={vi.fn()} />);
    expect(screen.getByLabelText("Price (USD)")).toHaveValue("5.00");

    rerender(<MoneyInput label="Price" currencyLabel="USD" valueCents={1000} onChangeCents={vi.fn()} />);

    expect(screen.getByLabelText("Price (USD)")).toHaveValue("10.00");
  });

  it("renders an externally-supplied error (e.g. a server validation failure) with the same accessible error treatment as a parse error", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} error="Rate must be at least 0." />);

    expect(screen.getByRole("alert")).toHaveTextContent("Rate must be at least 0.");
    expect(screen.getByLabelText("Price (USD)")).toHaveAttribute("aria-invalid", "true");
  });

  it("marks the field invalid (red border) when an externally-supplied error is present", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} error="Rate must be at least 0." />);

    expect(screen.getByLabelText("Price (USD)").className).toMatch(/(^| )border-error( |$)/);
  });

  it("a local parse error takes precedence over a stale externally-supplied error", async () => {
    const user = userEvent.setup();
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={null} onChangeCents={vi.fn()} error="Rate must be at least 0." />);

    await user.type(screen.getByLabelText("Price (USD)"), "-5");

    expect(screen.getByRole("alert")).toHaveTextContent(/negative/i);
  });

  it("shows no error styling at all when neither a parse error nor an externally-supplied error exists", () => {
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Price (USD)")).not.toHaveAttribute("aria-invalid");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<MoneyInput label="Price" currencyLabel="USD" valueCents={0} onChangeCents={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
