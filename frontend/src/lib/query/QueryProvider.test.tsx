import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { useQueryClient } from "@tanstack/react-query";
import { QueryProvider } from "./QueryProvider";
import { getQueryClient } from "./queryClient";

// FVS001-T11 smoke test only — proves the provider renders and establishes
// a working QueryClientProvider context. No business query exists yet
// (that's FVS001-T13a); ContextProbe/CaptureClient below just consume the
// plain context hook to prove wiring, not application behavior.

function ContextProbe() {
  const client = useQueryClient();
  return <div data-testid="probe">{client ? "has-client" : "no-client"}</div>;
}

describe("QueryProvider", () => {
  it("renders its children", () => {
    render(
      <QueryProvider>
        <p>child content</p>
      </QueryProvider>
    );

    expect(screen.getByText("child content")).toBeInTheDocument();
  });

  it("establishes a working QueryClientProvider context — a descendant can call useQueryClient() without crashing", () => {
    render(
      <QueryProvider>
        <ContextProbe />
      </QueryProvider>
    );

    expect(screen.getByTestId("probe")).toHaveTextContent("has-client");
  });

  it("provides the same queryClient instance to descendants as getQueryClient() returns in this module context", () => {
    function IdentityProbe() {
      const client = useQueryClient();
      return <div data-testid="identity">{String(client === getQueryClient())}</div>;
    }

    render(
      <QueryProvider>
        <IdentityProbe />
      </QueryProvider>
    );

    expect(screen.getByTestId("identity")).toHaveTextContent("true");
  });
});

describe("getQueryClient", () => {
  it("returns the same (singleton) instance across repeated calls in this browser/test environment", () => {
    expect(getQueryClient()).toBe(getQueryClient());
  });
});
