import { describe, it, expect } from "vitest";
import { isPaymentProviderAllowedFor } from "./paymentProviderGuard";

describe("isPaymentProviderAllowedFor (phase 6F mock-payment guard)", () => {
  it("allows the mock provider outside production builds", () => {
    expect(isPaymentProviderAllowedFor({ provider: "mock", nodeEnv: "development", allowMock: undefined })).toBe(true);
    expect(isPaymentProviderAllowedFor({ provider: "mock", nodeEnv: "test", allowMock: undefined })).toBe(true);
  });

  it("refuses the mock provider in a production build unless explicitly allowed", () => {
    expect(isPaymentProviderAllowedFor({ provider: "mock", nodeEnv: "production", allowMock: undefined })).toBe(false);
    expect(isPaymentProviderAllowedFor({ provider: " MOCK ", nodeEnv: "production", allowMock: "1" })).toBe(false);
    expect(isPaymentProviderAllowedFor({ provider: "mock", nodeEnv: "production", allowMock: "true" })).toBe(true);
  });

  it("never blocks another provider", () => {
    expect(isPaymentProviderAllowedFor({ provider: "some-real-provider", nodeEnv: "production", allowMock: undefined })).toBe(true);
  });
});
