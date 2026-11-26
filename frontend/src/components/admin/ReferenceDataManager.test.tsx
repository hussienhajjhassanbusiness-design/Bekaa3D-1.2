import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReferenceDataManager } from "./ReferenceDataManager";
import type { ReferenceDataEntityConfig, ReferenceDataEntry } from "./referenceDataTypes";

// FVS-010-IMPLEMENTATION-PLAN.md T02 — presentational only (no fetch, no
// TanStack Query, no production mutation). Parameterized across category/
// material/colour-shaped configs to prove the component owns zero
// per-entity branching — every difference comes from `config` (item 20 of
// the plan's own test matrix). Archive confirmation reuses the existing
// ConfirmDialog (FVS-007) rather than a new modal (T04).

const CATEGORY_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Category",
  entityLabelPlural: "Categories",
  emptyStateMessage: "No categories yet — create one.",
};

const MATERIAL_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Material",
  entityLabelPlural: "Materials",
  emptyStateMessage: "No materials yet — create one.",
};

const COLOUR_CONFIG: ReferenceDataEntityConfig = {
  entityLabelSingular: "Colour",
  entityLabelPlural: "Colours",
  emptyStateMessage: "No colours yet — create one.",
  hasSwatchField: true,
  swatchFieldLabel: "Hex value",
  renderSwatch: (value: string) => <span data-testid="swatch" style={{ backgroundColor: value }} />,
};

const CONFIGS = [CATEGORY_CONFIG, MATERIAL_CONFIG, COLOUR_CONFIG];

function makeEntry(overrides: Partial<ReferenceDataEntry> = {}): ReferenceDataEntry {
  return { id: "e-1", name: "Alpha", isArchived: false, ...overrides };
}

describe.each(CONFIGS)("ReferenceDataManager ($entityLabelPlural)", (config) => {
  it("renders the entity's plural label", () => {
    render(<ReferenceDataManager config={config} entries={[]} onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByRole("heading", { name: config.entityLabelPlural })).toBeInTheDocument();
  });

  it("shows the configured empty-state message when there are no entries", () => {
    render(<ReferenceDataManager config={config} entries={[]} onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText(config.emptyStateMessage)).toBeInTheDocument();
  });

  it("renders an entry's name", () => {
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("shows archived state as visible text, not color alone", () => {
    render(
      <ReferenceDataManager
        config={config}
        entries={[makeEntry({ isArchived: true })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
      />
    );
    expect(screen.getByText(/archived/i)).toBeInTheDocument();
  });

  it("keeps an archived entry in the list instead of removing it", () => {
    render(
      <ReferenceDataManager
        config={config}
        entries={[makeEntry({ isArchived: true })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
      />
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("disables further archiving for an already-archived entry", () => {
    render(
      <ReferenceDataManager
        config={config}
        entries={[makeEntry({ isArchived: true })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /archive/i })).toBeDisabled();
  });

  it("opens a create form when Add is activated", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[]} onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: new RegExp(`add ${config.entityLabelSingular}`, "i") }));

    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("opens an edit form pre-filled with the entry's data", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(screen.getByLabelText("Name")).toHaveValue("Alpha");
  });

  it("Cancel closes the form without calling onSave", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[]} onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: new RegExp(`add ${config.entityLabelSingular}`, "i") }));
    await user.type(screen.getByLabelText("Name"), "Draft text");
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });

  it("Save calls onSave with the typed name and a null editing id for a new entry", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[]} onSave={onSave} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: new RegExp(`add ${config.entityLabelSingular}`, "i") }));
    await user.type(screen.getByLabelText("Name"), "Beta");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ name: "Beta" }), null);
  });

  it("Save calls onSave with the editing entry's id when editing", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <ReferenceDataManager config={config} entries={[makeEntry({ id: "e-9" })]} onSave={onSave} onArchive={vi.fn()} />
    );

    await user.click(screen.getByRole("button", { name: /edit/i }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Renamed");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ name: "Renamed" }), "e-9");
  });

  it("disables Save while isSaving, preventing a duplicate submit", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[]} onSave={vi.fn()} onArchive={vi.fn()} isSaving />);

    await user.click(screen.getByRole("button", { name: new RegExp(`add ${config.entityLabelSingular}`, "i") }));

    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("shows an inline, normalized field error next to the Name field", async () => {
    const user = userEvent.setup();
    render(
      <ReferenceDataManager
        config={config}
        entries={[]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
        fieldErrors={{ name: "This name is already in use." }}
      />
    );

    await user.click(screen.getByRole("button", { name: new RegExp(`add ${config.entityLabelSingular}`, "i") }));

    expect(screen.getByText("This name is already in use.")).toBeInTheDocument();
  });

  it("clicking Archive opens a confirmation dialog", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("the confirmation dialog is the shared ConfirmDialog, not a new modal", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText(new RegExp(`archive ${config.entityLabelSingular}`, "i"))).toBeInTheDocument();
  });

  it("Cancel in the archive dialog closes it without calling onArchive", async () => {
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={onArchive} />);

    await user.click(screen.getByRole("button", { name: /archive/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onArchive).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Confirm in the archive dialog calls onArchive with the entry id", async () => {
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(
      <ReferenceDataManager
        config={config}
        entries={[makeEntry({ id: "e-7" })]}
        onSave={vi.fn()}
        onArchive={onArchive}
      />
    );

    await user.click(screen.getByRole("button", { name: /archive/i }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^archive$/i }));

    expect(onArchive).toHaveBeenCalledWith("e-7");
  });

  it("uses a responsive stacked-card row structure (FVS-007 pattern), not AdminTable's scroll-table", () => {
    render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />);
    const row = screen.getByText("Alpha").closest("li");
    expect(row?.className).toMatch(/flex-col/);
    expect(row?.className).toMatch(/tablet:flex-row/);
  });
});

describe("ReferenceDataManager (reversible enable/disable)", () => {
  it("does not render a toggle action when onToggleActive is not provided", () => {
    render(
      <ReferenceDataManager config={CATEGORY_CONFIG} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />
    );
    expect(screen.queryByRole("button", { name: /disable|enable/i })).not.toBeInTheDocument();
  });

  it("shows a Disable action for a live entry and calls onToggleActive(id, false)", async () => {
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <ReferenceDataManager
        config={CATEGORY_CONFIG}
        entries={[makeEntry({ isActive: true })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
        onToggleActive={onToggleActive}
      />
    );

    await user.click(screen.getByRole("button", { name: "Disable" }));

    expect(onToggleActive).toHaveBeenCalledWith("e-1", false);
  });

  it("shows an Enable action and a Disabled badge for a disabled entry, and calls onToggleActive(id, true)", async () => {
    const onToggleActive = vi.fn();
    const user = userEvent.setup();
    render(
      <ReferenceDataManager
        config={CATEGORY_CONFIG}
        entries={[makeEntry({ isActive: false })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
        onToggleActive={onToggleActive}
      />
    );

    expect(screen.getByText("Disabled")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enable" }));

    expect(onToggleActive).toHaveBeenCalledWith("e-1", true);
  });

  it("never shows the toggle action for an already-archived entry", () => {
    render(
      <ReferenceDataManager
        config={CATEGORY_CONFIG}
        entries={[makeEntry({ isArchived: true, isActive: false })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
        onToggleActive={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: /disable|enable/i })).not.toBeInTheDocument();
    // Archived takes precedence over the disabled badge — archive already
    // implies "not usable," so showing both would be redundant.
    expect(screen.queryByText("Disabled")).not.toBeInTheDocument();
  });
});

describe("ReferenceDataManager (safety)", () => {
  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(
      <ReferenceDataManager config={CATEGORY_CONFIG} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(
      <ReferenceDataManager config={CATEGORY_CONFIG} entries={[makeEntry()]} onSave={vi.fn()} onArchive={vi.fn()} />
    );
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("ReferenceDataManager (colour supplemental swatch)", () => {
  it("renders the supplemental swatch alongside the text label, never replacing it", () => {
    render(
      <ReferenceDataManager
        config={COLOUR_CONFIG}
        entries={[makeEntry({ name: "Red", swatchValue: "#ff0000" })]}
        onSave={vi.fn()}
        onArchive={vi.fn()}
      />
    );
    expect(screen.getByText("Red")).toBeInTheDocument();
    expect(screen.getByTestId("swatch")).toBeInTheDocument();
  });

  it("shows the configured swatch field in the create form", async () => {
    const user = userEvent.setup();
    render(<ReferenceDataManager config={COLOUR_CONFIG} entries={[]} onSave={vi.fn()} onArchive={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /add colour/i }));

    expect(screen.getByLabelText("Hex value")).toBeInTheDocument();
  });
});

describe.each([MATERIAL_CONFIG, COLOUR_CONFIG])(
  "ReferenceDataManager without a lifecycle config ($entityLabelPlural)",
  (config) => {
    it("keeps the single list: no tabs, archived rows stay in place with their badge", () => {
      render(
        <ReferenceDataManager
          config={config}
          entries={[makeEntry(), makeEntry({ id: "e-2", name: "Beta", isArchived: true })]}
          onSave={vi.fn()}
          onArchive={vi.fn()}
        />
      );
      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
      expect(screen.queryByRole("tabpanel")).not.toBeInTheDocument();
      expect(screen.getByText("Alpha")).toBeInTheDocument();
      expect(screen.getByText("Beta")).toBeInTheDocument();
    });

    it("closes the archive confirmation once the archive request settles", async () => {
      const user = userEvent.setup();
      let finish: () => void = () => {};
      const onArchive = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
      render(<ReferenceDataManager config={config} entries={[makeEntry()]} onSave={vi.fn()} onArchive={onArchive} />);

      await user.click(screen.getByRole("button", { name: /archive/i }));
      await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^archive$/i }));
      expect(onArchive).toHaveBeenCalledWith("e-1");
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      finish();
      await screen.findByRole("button", { name: /archive/i });
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  }
);
