import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import VerifyEmail from "./page";

describe("VerifyEmail (/verify-email route skeleton)", () => {
  it("renders a heading and placeholder content — no token handling yet (contract-gated, Task T09)", () => {
    render(<VerifyEmail />);

    expect(screen.getByRole("heading", { name: /verify your email/i })).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
