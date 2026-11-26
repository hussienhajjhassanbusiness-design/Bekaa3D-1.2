import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AdminColoursPage from "./page";
import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";

vi.mock("@/components/admin/AdminReferenceDataPage", () => ({
  AdminReferenceDataPage: vi.fn(() => null),
}));

describe("AdminColoursPage", () => {
  it("renders the colours resource with no swatch/hex field (the real contract has no colour-value field)", () => {
    render(<AdminColoursPage />);
    expect(screen.getByRole("heading", { name: "Colours" })).toBeInTheDocument();
    const call = vi.mocked(AdminReferenceDataPage).mock.calls[0]![0];
    expect(call.resource).toBe("colours");
    expect(call.config.hasSwatchField).toBeUndefined();
  });
});
