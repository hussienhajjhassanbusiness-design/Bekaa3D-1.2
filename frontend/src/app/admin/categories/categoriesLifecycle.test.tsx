import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminCategoriesPage from "./page";
import {
  useReferenceDataList,
  useReferenceDataCreate,
  useReferenceDataUpdate,
  useReferenceDataArchive,
} from "@/lib/admin/referenceData/useReferenceData";
import type { ReferenceDataEntry } from "@/components/admin/referenceDataTypes";

// Admin → Categories: Active / Disabled / Archived tabs over the real
// reference-data hooks (mocked here). Archiving is terminal in the backend
// (no restore endpoint, PATCH on an archived row is 409), so the Archived tab
// is read-only and nothing offers Restore.

vi.mock("@/lib/admin/referenceData/useReferenceData", () => ({
  useReferenceDataList: vi.fn(),
  useReferenceDataCreate: vi.fn(),
  useReferenceDataUpdate: vi.fn(),
  useReferenceDataArchive: vi.fn(),
}));

const mockedList = vi.mocked(useReferenceDataList);
const mockedCreate = vi.mocked(useReferenceDataCreate);
const mockedUpdate = vi.mocked(useReferenceDataUpdate);
const mockedArchive = vi.mocked(useReferenceDataArchive);

const TOYS: ReferenceDataEntry = { id: "c1", name: "Toys", isArchived: false, isActive: true, swatchValue: "toys" };
const TOOLS: ReferenceDataEntry = { id: "c2", name: "Tools", isArchived: false, isActive: true, swatchValue: "tools" };
const DECOR: ReferenceDataEntry = { id: "c3", name: "Decor", isArchived: false, isActive: false, swatchValue: "decor" };
const OLD: ReferenceDataEntry = { id: "c4", name: "Old range", isArchived: true, isActive: false, swatchValue: "old" };
const ALL = [TOYS, TOOLS, DECOR, OLD];

function list(entries: ReferenceDataEntry[] | undefined, overrides: Record<string, unknown> = {}) {
  mockedList.mockReturnValue({ data: entries, isLoading: false, isError: false, ...overrides } as never);
}

function setup({
  entries = ALL,
  archive = vi.fn().mockResolvedValue(undefined),
  update = vi.fn().mockResolvedValue({}),
}: { entries?: ReferenceDataEntry[]; archive?: ReturnType<typeof vi.fn>; update?: ReturnType<typeof vi.fn> } = {}) {
  list(entries);
  mockedArchive.mockReturnValue({ mutateAsync: archive, isPending: false } as never);
  mockedUpdate.mockReturnValue({ mutateAsync: update, isPending: false } as never);
  const user = userEvent.setup();
  const view = render(<AdminCategoriesPage />);
  return { user, archive, update, ...view };
}

const tab = (name: RegExp) => screen.getByRole("tab", { name });
const panel = () => screen.getByRole("tabpanel");

beforeEach(() => {
  mockedList.mockReset();
  mockedCreate.mockReset();
  mockedUpdate.mockReset();
  mockedArchive.mockReset();
  mockedCreate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
});

describe("Admin categories — lifecycle tabs", () => {
  it("shows Active, Disabled and Archived tabs with counts; Active is selected by default", () => {
    setup();
    expect(screen.getByRole("tablist", { name: "Categories by status" })).toBeInTheDocument();
    expect(tab(/^Active/)).toHaveAccessibleName("Active, 2 categories");
    expect(tab(/^Disabled/)).toHaveAccessibleName("Disabled, 1 category");
    expect(tab(/^Archived/)).toHaveAccessibleName("Archived, 1 category");
    expect(tab(/^Active/)).toHaveAttribute("aria-selected", "true");
    expect(panel()).toHaveAccessibleName(/^Active/);
    expect(within(panel()).getByText("Toys")).toBeInTheDocument();
    expect(within(panel()).getByText("Tools")).toBeInTheDocument();
    expect(within(panel()).queryByText("Decor")).not.toBeInTheDocument();
    expect(within(panel()).queryByText("Old range")).not.toBeInTheDocument();
  });

  it("offers Edit, Disable and Archive on an active category", () => {
    setup();
    for (const name of ["Edit Toys", "Disable Toys", "Archive Toys"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
    expect(screen.queryByRole("button", { name: /enable toys/i })).not.toBeInTheDocument();
  });

  it("offers Edit, Enable and Archive on a disabled category", async () => {
    const { user } = setup();
    await user.click(tab(/^Disabled/));
    expect(within(panel()).getByText("Decor")).toBeInTheDocument();
    for (const name of ["Edit Decor", "Enable Decor", "Archive Decor"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
  });

  it("shows archived categories read-only, explains why, and never offers Restore", async () => {
    const { user } = setup();
    await user.click(tab(/^Archived/));
    expect(within(panel()).getByText("Old range")).toBeInTheDocument();
    expect(within(panel()).getByText("Archived")).toBeInTheDocument();
    expect(within(panel()).getByText(/can't be edited or restored/)).toBeInTheDocument();
    expect(within(panel()).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore/i })).not.toBeInTheDocument();
  });

  it("moves between tabs with the arrow keys, Home and End", async () => {
    const { user } = setup();
    tab(/^Active/).focus();
    await user.keyboard("{ArrowRight}");
    expect(tab(/^Disabled/)).toHaveFocus();
    expect(tab(/^Disabled/)).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tab(/^Archived/)).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(tab(/^Active/)).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(tab(/^Archived/)).toHaveFocus();
    await user.keyboard("{Home}");
    expect(tab(/^Active/)).toHaveAttribute("aria-selected", "true");
    expect(tab(/^Disabled/)).toHaveAttribute("tabindex", "-1");
  });

  it("shows an empty message per tab", async () => {
    const { user } = setup({ entries: [TOYS] });
    await user.click(tab(/^Disabled/));
    expect(within(panel()).getByText(/No disabled categories/)).toBeInTheDocument();
    await user.click(tab(/^Archived/));
    expect(within(panel()).getByText("No archived categories.")).toBeInTheDocument();
  });

  it("shows the loading state with placeholder counts", () => {
    list(undefined, { isLoading: true });
    mockedArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    mockedUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    render(<AdminCategoriesPage />);
    expect(tab(/^Active/)).toHaveAccessibleName("Active, loading");
    expect(within(panel()).getByRole("status")).toHaveTextContent("Loading…");
  });

  it("shows the load error state", () => {
    list(undefined, { isError: true });
    mockedArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    mockedUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    render(<AdminCategoriesPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load categories.");
  });
});

describe("Admin categories — archive", () => {
  it("asks for confirmation and explains the consequences before any request", async () => {
    const { user, archive } = setup();
    await user.click(screen.getByRole("button", { name: "Archive Toys" }));

    const dialog = screen.getByRole("dialog", { name: "Archive “Toys”?" });
    expect(dialog).toHaveAccessibleDescription(/permanent/);
    expect(dialog).toHaveAccessibleDescription(/disappears from the storefront/);
    expect(dialog).toHaveAccessibleDescription(/slug is released/);
    expect(dialog).toHaveAccessibleDescription(/can't be edited, enabled or restored/);
    expect(dialog).toHaveAccessibleDescription(/live product still uses can't be archived/);
    expect(archive).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(archive).not.toHaveBeenCalled();
  });

  it("archives on confirm, closes the dialog, reports success, and the category moves to Archived with updated counts", async () => {
    let finish: () => void = () => {};
    const archive = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    const { user, rerender } = setup({ archive });
    await user.click(screen.getByRole("button", { name: "Archive Toys" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));

    expect(archive).toHaveBeenCalledWith("c1");
    // Still open while the request is in flight.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("“Toys” was archived. It's now in the Archived tab.");

    // The refetched list (what the mutation's invalidation brings back).
    list([{ ...TOYS, isArchived: true, isActive: false }, TOOLS, DECOR, OLD]);
    rerender(<AdminCategoriesPage />);
    expect(tab(/^Active/)).toHaveAccessibleName("Active, 1 category");
    expect(tab(/^Archived/)).toHaveAccessibleName("Archived, 2 categories");
    await user.click(tab(/^Archived/));
    expect(within(panel()).getByText("Toys")).toBeInTheDocument();
  });

  it("a refused archive (category in use) shows a safe error, keeps the category active and claims no success", async () => {
    const archive = vi.fn().mockRejectedValue({ kind: "http", status: 409, code: "CATEGORY_IN_USE", message: "x" });
    const { user } = setup({ archive });
    await user.click(screen.getByRole("button", { name: "Archive Toys" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("still used by a live product");
    expect(screen.queryByText(/was archived/)).not.toBeInTheDocument();
    expect(within(panel()).getByText("Toys")).toBeInTheDocument();
  });
});

describe("Admin categories — enable and disable", () => {
  it("disabling sends is_active false and reports where the category went", async () => {
    const { user, update } = setup();
    await user.click(screen.getByRole("button", { name: "Disable Toys" }));
    expect(update).toHaveBeenCalledWith({ id: "c1", input: { isActive: false } });
    expect(await screen.findByRole("status")).toHaveTextContent("“Toys” was disabled.");
  });

  it("enabling a disabled category sends is_active true", async () => {
    const { user, update } = setup();
    await user.click(tab(/^Disabled/));
    await user.click(screen.getByRole("button", { name: "Enable Decor" }));
    expect(update).toHaveBeenCalledWith({ id: "c3", input: { isActive: true } });
    expect(await screen.findByRole("status")).toHaveTextContent("“Decor” was enabled.");
  });
});
