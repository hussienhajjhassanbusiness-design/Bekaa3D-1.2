import { describe, it, expect } from "vitest";
import {
  describePromotionStatus,
  discountAmount,
  discountBadge,
  discountHeadline,
  promotionScopeLabel,
} from "./promotionFormat";

describe("promotion labels (display only)", () => {
  it("formats a percentage discount", () => {
    expect(discountHeadline("percentage", 20, "USD", "en-US")).toBe("20% OFF");
    expect(discountBadge("percentage", 20, "USD", "en-US")).toBe("-20%");
  });

  it("formats a fixed discount from cents, without trailing zeros for whole amounts", () => {
    expect(discountHeadline("fixed", 500, "USD", "en-US")).toBe("$5 OFF");
    expect(discountAmount("fixed", 550, "USD", "en-US")).toBe("$5.50");
    expect(discountBadge("fixed", 500, "USD", "en-US")).toBe("-$5");
  });

  it("names every scope and server status", () => {
    expect(promotionScopeLabel("all")).toBe("All products");
    expect(promotionScopeLabel("selected")).toBe("Selected products");
    expect(describePromotionStatus("scheduled").label).toBe("Scheduled");
    expect(describePromotionStatus("active").label).toBe("Active");
    expect(describePromotionStatus("ended").label).toBe("Ended");
    expect(describePromotionStatus("inactive").label).toBe("Inactive");
  });
});
