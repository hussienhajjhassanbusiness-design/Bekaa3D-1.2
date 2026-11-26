import { describe, it, expect } from "vitest";
import { dayEndExclusive, dayStart } from "./dateRange";

describe("admin date range", () => {
  it("sends aware instants: local midnight, and the next day's midnight for the exclusive end", () => {
    const start = dayStart("2026-11-10");
    const end = dayEndExclusive("2026-11-10");
    expect(start).toBe(new Date(2026, 10, 10).toISOString());
    expect(end).toBe(new Date(2026, 10, 11).toISOString());
    expect(start!.endsWith("Z")).toBe(true);
  });

  it("omits empty or malformed values", () => {
    expect(dayStart("")).toBeUndefined();
    expect(dayStart("10/11/2026")).toBeUndefined();
    expect(dayEndExclusive("2026-13-99")).not.toBe("2026-13-99");
  });
});
