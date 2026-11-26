import { describe, it, expect } from "vitest";
import { CUSTOM_REQUEST_STATUSES, describeCustomRequestStatus, describeOutcome, getCustomRequestActions } from "./customRequestPipeline";

// Backend 2dfb27b domain/custom_request.py PIPELINE — the only edges.
describe("getCustomRequestActions", () => {
  it("mirrors the server's edges exactly", () => {
    const edges = Object.fromEntries(CUSTOM_REQUEST_STATUSES.map((s) => [s, getCustomRequestActions(s).map((a) => a.target)]));
    expect(edges).toEqual({
      new: ["contacted"],
      contacted: ["quoted", "lost"],
      quoted: ["in_progress", "lost"],
      in_progress: ["completed"],
      completed: ["closed"],
      closed: [],
      lost: [],
    });
  });

  it("asks for a quote only when moving to quoted, and marks lost as destructive", () => {
    const contacted = getCustomRequestActions("contacted");
    expect(contacted.find((a) => a.target === "quoted")).toMatchObject({ label: "Record quote", needsQuote: true });
    expect(contacted.find((a) => a.target === "lost")).toMatchObject({ needsQuote: false, destructive: true });
    expect(getCustomRequestActions("quoted").every((a) => !a.needsQuote)).toBe(true);
  });
});

describe("describe helpers", () => {
  it("labels statuses and outcomes, tolerating unknown values", () => {
    expect(describeCustomRequestStatus("in_progress")).toEqual({ label: "In progress", tone: "positive" });
    expect(describeCustomRequestStatus("archived")).toEqual({ label: "archived", tone: "neutral" });
    expect([describeOutcome("won"), describeOutcome("lost"), describeOutcome(null)]).toEqual(["Won", "Lost", "Open"]);
  });
});
