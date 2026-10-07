import { describe, it, expect } from "vitest";
import { getNextContactMessageAction, describeContactMessageStatus, type ContactMessageStatus } from "./contactMessageWorkflow";

const ALL_STATUSES: readonly ContactMessageStatus[] = ["new", "read", "replied", "archived"];

// FVS-017-IMPLEMENTATION-PLAN.md T01 — frontend-normalized workflow
// only. "new"/"read"/"replied"/"archived" are UI-normalized concepts,
// not claimed backend enum literals (plan §1) — a future API adapter
// maps the real backend representation onto this union. The linear
// sequence (new → read → replied → archived, no skips, no reverse
// transitions) is confirmed PRODUCT behavior
// (FRONTEND-VERTICAL-SLICE-PLAN.md's own FVS-017 capability line:
// "new → read → replied → archived").

describe("getNextContactMessageAction", () => {
  it("exposes Mark read as the only action for a new message", () => {
    expect(getNextContactMessageAction("new")).toEqual({ nextStatus: "read", label: "Mark read" });
  });

  it("exposes Mark replied as the only action for a read message", () => {
    expect(getNextContactMessageAction("read")).toEqual({ nextStatus: "replied", label: "Mark replied" });
  });

  it("exposes Archive as the only action for a replied message", () => {
    expect(getNextContactMessageAction("replied")).toEqual({ nextStatus: "archived", label: "Archive" });
  });

  it("exposes no action for an archived message", () => {
    expect(getNextContactMessageAction("archived")).toBeNull();
  });
});

describe("describeContactMessageStatus", () => {
  it("gives each status a human-readable label", () => {
    expect(describeContactMessageStatus("new").label).toBe("New");
    expect(describeContactMessageStatus("read").label).toBe("Read");
    expect(describeContactMessageStatus("replied").label).toBe("Replied");
    expect(describeContactMessageStatus("archived").label).toBe("Archived");
  });

  it("gives each status a bounded tone, never an arbitrary color string", () => {
    for (const status of ALL_STATUSES) {
      expect(["neutral", "positive", "negative", "warning"]).toContain(describeContactMessageStatus(status).tone);
    }
  });
});
