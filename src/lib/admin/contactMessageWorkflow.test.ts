import { describe, it, expect } from "vitest";
import { describeContactMessageStatus, getContactMessageActions, isContactMessageStatus } from "./contactMessageWorkflow";

// Backend 2dfb27b contact_message.py can_transition: forward only, skips
// allowed; staying put is a no-op (never offered).
describe("getContactMessageActions", () => {
  it("offers every later status from new, nearest first", () => {
    expect(getContactMessageActions("new")).toEqual([
      { nextStatus: "read", label: "Mark read" },
      { nextStatus: "replied", label: "Mark replied" },
      { nextStatus: "archived", label: "Archive" },
    ]);
  });

  it("never offers a backwards or same-status move", () => {
    expect(getContactMessageActions("replied").map((a) => a.nextStatus)).toEqual(["archived"]);
    expect(getContactMessageActions("read").map((a) => a.nextStatus)).toEqual(["replied", "archived"]);
  });

  it("offers nothing once archived", () => {
    expect(getContactMessageActions("archived")).toEqual([]);
  });
});

describe("describeContactMessageStatus", () => {
  it("labels each backend status with visible text", () => {
    expect(describeContactMessageStatus("new")).toEqual({ label: "New", tone: "warning" });
    expect(describeContactMessageStatus("replied")).toEqual({ label: "Replied", tone: "positive" });
  });

  it("renders an unknown future status as itself rather than crashing", () => {
    expect(describeContactMessageStatus("escalated")).toEqual({ label: "escalated", tone: "neutral" });
    expect(isContactMessageStatus("escalated")).toBe(false);
  });
});
