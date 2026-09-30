import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Register from "./page";

describe("Register (/register route skeleton)", () => {
  it("renders a heading and placeholder content — no form yet (contract-gated, Task T08)", () => {
    render(<Register />);

    expect(screen.getByRole("heading", { name: /create your account/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
