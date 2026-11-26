import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AdminMaterialsPage from "./page";
import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";

vi.mock("@/components/admin/AdminReferenceDataPage", () => ({
  AdminReferenceDataPage: vi.fn(() => null),
}));

describe("AdminMaterialsPage", () => {
  it("renders the materials resource with no swatch field", () => {
    render(<AdminMaterialsPage />);
    expect(screen.getByRole("heading", { name: "Materials" })).toBeInTheDocument();
    const call = vi.mocked(AdminReferenceDataPage).mock.calls[0]![0];
    expect(call.resource).toBe("materials");
    expect(call.config.hasSwatchField).toBeUndefined();
  });
});
