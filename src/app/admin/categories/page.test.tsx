import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AdminCategoriesPage from "./page";
import { AdminReferenceDataPage } from "@/components/admin/AdminReferenceDataPage";

vi.mock("@/components/admin/AdminReferenceDataPage", () => ({
  AdminReferenceDataPage: vi.fn(() => null),
}));

describe("AdminCategoriesPage", () => {
  it("renders the categories resource with a slug swatch field", () => {
    render(<AdminCategoriesPage />);
    expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
    const call = vi.mocked(AdminReferenceDataPage).mock.calls[0]![0];
    expect(call.resource).toBe("categories");
    expect(call.config.hasSwatchField).toBe(true);
  });
});
