"use client";

import { FIELD_ERROR_CLASSES, FIELD_HINT_CLASSES, FIELD_LABEL_CLASSES, FieldErrorIcon, fieldControlClasses } from "./fieldStyles";
import { useEffect, useId, useRef, useState, type ChangeEvent } from "react";

export interface MoneyInputProps {
  label: string;
  // Explicit, required seam — never hardcoded. vertical-slice-plan.md §2
  // lists "Confirm USD settlement/support" as a still-open external item,
  // so this component must not assume USD (or any currency) itself.
  currencyLabel: string;
  valueCents: number | null;
  onChangeCents: (next: number | null) => void;
  hint?: string;
  // Externally-supplied error (e.g. a server validation failure) —
  // rendered with the exact same accessible treatment as this
  // component's own internal parse error. A local parse error always
  // takes precedence (it reflects the text currently on screen; a
  // stale external error about a prior value would be misleading).
  // The caller owns clearing this once it's no longer applicable
  // (same convention TextField's own `error` prop already uses).
  error?: string;
}

export type MoneyParseResult =
  | { ok: true; cents: number }
  | { ok: false; reason: "invalid" | "negative" | "too-many-decimals" };

const DECIMAL_PATTERN = /^(-?)(\d+)(?:\.(\d+))?$/;

// #SHARED-MONEY-INPUT
//
// Cents-safe decimal-string parser — deliberately string-based, never
// `parseFloat(text) * 100`, so values like "0.10" can never produce a
// floating-point artifact (9 or 11 cents instead of 10). Reused by every
// future price-entering admin UI (products, offers, refunds — see
// FRONTEND-VERTICAL-SLICE-PLAN.md's MoneyInput reuse list).
//
// Rejects (does not round) more than 2 decimal digits. This is a
// deliberate, recorded discrepancy: vertical-slice-plan.md's VS-011 only
// says "money validation" as a test name, and
// FRONTEND-VERTICAL-SLICE-PLAN.md only says "cents rounding" in its own
// test-summary line — neither defines an actual rounding rule (half-up,
// banker's, truncate, etc.). Inventing one here would silently encode an
// unconfirmed financial policy, so >2-decimal input is rejected with an
// explicit message instead (FVS-011-IMPLEMENTATION-PLAN.md §0/§5).
export function parseDecimalToCents(raw: string): MoneyParseResult {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, reason: "invalid" };
  }

  const match = DECIMAL_PATTERN.exec(trimmed);
  if (!match) {
    return { ok: false, reason: "invalid" };
  }

  const [, sign, wholePart, fractionalPart = ""] = match;
  if (sign === "-") {
    return { ok: false, reason: "negative" };
  }
  if (fractionalPart.length > 2) {
    return { ok: false, reason: "too-many-decimals" };
  }

  const paddedFraction = fractionalPart.padEnd(2, "0");
  const cents = Number(wholePart) * 100 + Number(paddedFraction);
  return { ok: true, cents };
}

function formatCentsToDecimal(cents: number): string {
  return (cents / 100).toFixed(2);
}

const ERROR_MESSAGES: Record<Exclude<MoneyParseResult, { ok: true }>["reason"], string> = {
  invalid: "Enter a valid amount.",
  negative: "Enter a positive amount — negative amounts aren't allowed.",
  "too-many-decimals": "Enter an amount with at most 2 decimal places.",
};

export function MoneyInput({ label, currencyLabel, valueCents, onChangeCents, hint, error: externalError }: MoneyInputProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const [rawText, setRawText] = useState(() => (valueCents === null ? "" : formatCentsToDecimal(valueCents)));
  const [parseError, setParseError] = useState<string | null>(null);
  // A local parse error always takes precedence over a stale
  // externally-supplied one — it reflects the text currently on
  // screen, which a prior server error does not.
  const displayedError = parseError ?? externalError ?? null;
  // Tracks the cents value this component itself last emitted, so the
  // external-sync effect below can tell "the parent re-rendered with the
  // value we just emitted" (skip — would clobber in-progress typing like
  // "12.3") apart from "the parent changed the value independently"
  // (resync the displayed text).
  const lastEmittedRef = useRef<number | null>(valueCents);

  useEffect(() => {
    if (valueCents !== lastEmittedRef.current) {
      lastEmittedRef.current = valueCents;
      setRawText(valueCents === null ? "" : formatCentsToDecimal(valueCents));
      setParseError(null);
    }
  }, [valueCents]);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.value;
    setRawText(next);

    if (next.trim() === "") {
      setParseError(null);
      lastEmittedRef.current = null;
      onChangeCents(null);
      return;
    }

    const result = parseDecimalToCents(next);
    if (!result.ok) {
      // Deliberately does not call onChangeCents here — an unparseable
      // in-progress edit (e.g. "12.") must never emit a corrupted cents
      // value; the last valid value stands until the user fixes it.
      setParseError(ERROR_MESSAGES[result.reason]);
      return;
    }

    setParseError(null);
    lastEmittedRef.current = result.cents;
    onChangeCents(result.cents);
  }

  const describedBy = [hint ? hintId : null, displayedError ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={inputId} className={FIELD_LABEL_CLASSES}>
        {label} ({currencyLabel})
      </label>
      <input
        id={inputId}
        type="text"
        inputMode="decimal"
        value={rawText}
        onChange={handleChange}
        aria-describedby={describedBy}
        aria-invalid={displayedError ? true : undefined}
        className={`mt-2 ${fieldControlClasses(Boolean(displayedError))}`}
      />
      {hint && (
        <p id={hintId} className={FIELD_HINT_CLASSES}>
          {hint}
        </p>
      )}
      {displayedError && (
        <p id={errorId} role="alert" className={FIELD_ERROR_CLASSES}>
          <FieldErrorIcon />
          {displayedError}
        </p>
      )}
    </div>
  );
}
