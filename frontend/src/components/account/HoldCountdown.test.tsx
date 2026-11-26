import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { HoldCountdown } from "./HoldCountdown";

const NOW = Date.parse("2026-11-10T10:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("HoldCountdown", () => {
  it("counts down from the server's hold_expires_at", () => {
    render(<HoldCountdown expiresAt="2026-11-10T10:12:05Z" />);
    expect(screen.getByText(/time left to complete payment/i)).toHaveTextContent("12:05");
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(screen.getByText(/time left to complete payment/i)).toHaveTextContent("12:00");
  });

  it("at zero: calls onElapsed ONCE, claims no expiry, and stops ticking", () => {
    const onElapsed = vi.fn();
    render(<HoldCountdown expiresAt="2026-11-10T10:00:03Z" onElapsed={onElapsed} />);
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(onElapsed).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/time to complete payment is up/i)).toBeInTheDocument();
    expect(screen.getByText(/may be released/i)).toBeInTheDocument();
    expect(screen.queryByText(/expired|cancelled|was released/i)).not.toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(onElapsed).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("an already-past deadline shows the conditional copy and asks for a re-read", () => {
    const onElapsed = vi.fn();
    render(<HoldCountdown expiresAt="2026-11-10T09:00:00Z" onElapsed={onElapsed} />);
    expect(screen.getByText(/time to complete payment is up/i)).toBeInTheDocument();
    expect(onElapsed).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for an unparseable timestamp", () => {
    const { container } = render(<HoldCountdown expiresAt="not-a-date" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows hours when more than an hour remains", () => {
    render(<HoldCountdown expiresAt="2026-11-10T11:05:09Z" />);
    expect(screen.getByText(/time left/i)).toHaveTextContent("1:05:09");
  });
});
