import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ResendVerification from "./page";

describe("ResendVerification (/verify-email/resend route skeleton)", () => {
  it("renders a heading and placeholder content — no form/cooldown yet (contract-gated, Task T10)", () => {
    render(<ResendVerification />);

    expect(screen.getByRole("heading", { name: /resend verification email/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
