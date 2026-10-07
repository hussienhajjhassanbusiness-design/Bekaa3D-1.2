import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetVersionList } from "./AssetVersionList";
import type { AssetVersion } from "@/lib/admin/assetVersionWorkflow";

// FVS-018-IMPLEMENTATION-PLAN.md T03 — presentational only, no network.
// Publish is disabled (not just discouraged) per
// #SECURITY-ASSET-PUBLISH-GATE's pure helpers; this component never
// optimistically marks a version current itself — `onPublish` is a
// pure callback, and the parent/server decides the real outcome.
// T02 (ScanStatusBadge) is absorbed here via direct `StatusBadge` reuse
// (describeScanStatus/describeAssetVersionState + <StatusBadge>) — no
// separate wrapper component, since StatusBadge's generalized
// {label, tone} API already fits cleanly (see plan §5/T02).

function makeVersion(overrides: Partial<AssetVersion> = {}): AssetVersion {
  return {
    id: "v-1",
    label: "Version 1",
    state: "pending",
    files: [{ id: "f-1", displayName: "model.stl", scanStatus: "clean" }],
    ...overrides,
  };
}

describe("AssetVersionList", () => {
  it("shows a Pending scan badge for a pending file", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ files: [{ id: "f-1", displayName: "a.stl", scanStatus: "pending" }] })]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.getByText("Pending scan")).toBeInTheDocument();
  });

  it("shows a Clean badge for a clean file", () => {
    render(<AssetVersionList versions={[makeVersion()]} onPublish={vi.fn()} />);
    expect(screen.getByText("Clean")).toBeInTheDocument();
  });

  it("shows an Infected badge for an infected file", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ files: [{ id: "f-1", displayName: "a.stl", scanStatus: "infected" }] })]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.getByText("Infected")).toBeInTheDocument();
  });

  it("identifies the current version", () => {
    render(<AssetVersionList versions={[makeVersion({ state: "current" })]} onPublish={vi.fn()} />);
    expect(screen.getByText("Current")).toBeInTheDocument();
  });

  it("identifies a superseded version", () => {
    render(<AssetVersionList versions={[makeVersion({ state: "superseded" })]} onPublish={vi.fn()} />);
    expect(screen.getByText("Superseded")).toBeInTheDocument();
  });

  it("enables Publish for a pending version whose files are all clean", () => {
    render(<AssetVersionList versions={[makeVersion({ state: "pending" })]} onPublish={vi.fn()} />);
    expect(screen.getByRole("button", { name: /publish/i })).not.toBeDisabled();
  });

  it("disables Publish while any file is pending", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ state: "pending", files: [{ id: "f-1", displayName: "a.stl", scanStatus: "pending" }] })]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /publish/i })).toBeDisabled();
  });

  it("disables Publish while any file is infected", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ state: "pending", files: [{ id: "f-1", displayName: "a.stl", scanStatus: "infected" }] })]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /publish/i })).toBeDisabled();
  });

  it("disables Publish for a mixed pending+clean bundle", () => {
    render(
      <AssetVersionList
        versions={[
          makeVersion({
            state: "pending",
            files: [
              { id: "f-1", displayName: "a.stl", scanStatus: "clean" },
              { id: "f-2", displayName: "b.stl", scanStatus: "pending" },
            ],
          }),
        ]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /publish/i })).toBeDisabled();
  });

  it("disables Publish for an empty bundle", () => {
    render(<AssetVersionList versions={[makeVersion({ state: "pending", files: [] })]} onPublish={vi.fn()} />);
    expect(screen.getByRole("button", { name: /publish/i })).toBeDisabled();
  });

  it("shows the disabled reason as visible text linked via aria-describedby", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ state: "pending", files: [{ id: "f-1", displayName: "a.stl", scanStatus: "pending" }] })]}
        onPublish={vi.fn()}
      />
    );
    const button = screen.getByRole("button", { name: /publish/i });
    const describedById = button.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    expect(document.getElementById(describedById!)?.textContent).toMatch(/scan/i);
  });

  it("calls onPublish with the exact version id", async () => {
    const onPublish = vi.fn();
    const user = userEvent.setup();
    render(<AssetVersionList versions={[makeVersion({ id: "v-42", state: "pending" })]} onPublish={onPublish} />);

    await user.click(screen.getByRole("button", { name: /publish/i }));

    expect(onPublish).toHaveBeenCalledWith("v-42");
  });

  it("renders no Publish action for a current or superseded version", () => {
    render(
      <AssetVersionList
        versions={[makeVersion({ id: "v-1", state: "current" }), makeVersion({ id: "v-2", state: "superseded" })]}
        onPublish={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: /publish/i })).not.toBeInTheDocument();
  });

  it("exposes a polite aria-live summary of per-version scan status for screen-reader admins", () => {
    render(
      <AssetVersionList
        versions={[
          makeVersion({
            state: "pending",
            files: [
              { id: "f-1", displayName: "a.stl", scanStatus: "clean" },
              { id: "f-2", displayName: "b.stl", scanStatus: "pending" },
            ],
          }),
        ]}
        onPublish={vi.fn()}
      />
    );
    const regions = screen.getAllByRole("status");
    const summary = regions.find((region) => /clean/i.test(region.textContent ?? "") && /pending/i.test(region.textContent ?? ""));
    expect(summary).toBeTruthy();
    expect(summary).toHaveAttribute("aria-live", "polite");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AssetVersionList versions={[makeVersion()]} onPublish={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<AssetVersionList versions={[makeVersion()]} onPublish={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
