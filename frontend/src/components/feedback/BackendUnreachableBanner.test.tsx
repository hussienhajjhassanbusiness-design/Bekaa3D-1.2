import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BackendUnreachableBanner } from "./BackendUnreachableBanner";
import { useReadiness } from "@/lib/health/useReadiness";

// FVS001-T13b — mock the hook, not the network. T13a already proved
// useReadiness's own fetching/polling/retry behavior; this file tests
// presentation only, given each of T13a's real, committed return shapes.
vi.mock("@/lib/health/useReadiness", () => ({
  useReadiness: vi.fn(),
}));

const mockedUseReadiness = vi.mocked(useReadiness);

beforeEach(() => {
  mockedUseReadiness.mockReset();
});

describe("BackendUnreachableBanner", () => {
  it("renders LoadingSpinner during the initial load, with no readiness-failure copy present", () => {
    mockedUseReadiness.mockReturnValue({ state: undefined, isLoading: true });

    render(<BackendUnreachableBanner />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/not ready/i)).toBeNull();
    expect(screen.queryByText(/could not be reached/i)).toBeNull();
    expect(screen.queryByText(/timed out/i)).toBeNull();
  });

  it("renders nothing when ready", () => {
    mockedUseReadiness.mockReturnValue({ state: "ready", isLoading: false });

    const { container } = render(<BackendUnreachableBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders 'not ready' copy with role=status/aria-live=polite, never role=alert", () => {
    mockedUseReadiness.mockReturnValue({ state: "not-ready", isLoading: false });

    render(<BackendUnreachableBanner />);

    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent(/reachable but not ready/i);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders 'unreachable' copy with role=alert/aria-live=assertive", () => {
    mockedUseReadiness.mockReturnValue({ state: "unreachable", isLoading: false });

    render(<BackendUnreachableBanner />);

    const region = screen.getByRole("alert");
    expect(region).toHaveAttribute("aria-live", "assertive");
    expect(region).toHaveTextContent(/could not be reached/i);
  });

  it("renders distinct 'timeout' copy with role=alert/aria-live=assertive", () => {
    mockedUseReadiness.mockReturnValue({ state: "timeout", isLoading: false });

    render(<BackendUnreachableBanner />);

    const region = screen.getByRole("alert");
    expect(region).toHaveAttribute("aria-live", "assertive");
    expect(region).toHaveTextContent(/timed out/i);
  });

  it("uses genuinely distinct copy for unreachable vs. timeout, not identical text merged into one message", () => {
    mockedUseReadiness.mockReturnValue({ state: "unreachable", isLoading: false });
    const { unmount } = render(<BackendUnreachableBanner />);
    const unreachableText = screen.getByRole("alert").textContent;
    unmount();

    mockedUseReadiness.mockReturnValue({ state: "timeout", isLoading: false });
    render(<BackendUnreachableBanner />);
    const timeoutText = screen.getByRole("alert").textContent;

    expect(unreachableText).not.toBe(timeoutText);
  });

  it("never invents a specific backend-failure cause not confirmed by the backend contract", () => {
    mockedUseReadiness.mockReturnValue({ state: "not-ready", isLoading: false });

    render(<BackendUnreachableBanner />);

    const text = screen.getByRole("status").textContent ?? "";
    expect(text).not.toMatch(/database|migration|dependency|queue|redis/i);
  });

  it("consumes useReadiness's normalized state only — never renders a raw transport-level detail", () => {
    mockedUseReadiness.mockReturnValue({ state: "unreachable", isLoading: false });

    render(<BackendUnreachableBanner />);

    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).not.toMatch(/typeerror|econnrefused|localhost|stack/i);
  });
});
