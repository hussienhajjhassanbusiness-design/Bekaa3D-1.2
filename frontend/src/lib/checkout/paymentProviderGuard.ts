// #SECURITY-MOCK-PAYMENT-GUARD (phase 6F)
//
// REAL ONLINE PAYMENT IS NOT BUILT (backend VS-032). The only online
// provider today is the backend's `mock`, which the backend itself refuses
// to boot outside development, test and staging
// (payments/infrastructure/providers/factory.py). As defence in depth, a
// PRODUCTION build of this frontend never sends a shopper to a `mock`
// provider's page, even if it is pointed at a backend that runs one: the
// response is then shown as "the payment page isn't available, nothing has
// been charged". A staging build that must exercise the mock flow opts in
// explicitly with NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS=true (inlined at build).
//
// The provider name is the server's own `payment.provider`; nothing is
// inferred from the URL.
export const MOCK_PAYMENT_PROVIDER = "mock";

export interface PaymentProviderGuardInput {
  provider: string;
  nodeEnv: string | undefined;
  allowMock: string | undefined;
}

export function isPaymentProviderAllowedFor({ provider, nodeEnv, allowMock }: PaymentProviderGuardInput): boolean {
  if (provider.trim().toLowerCase() !== MOCK_PAYMENT_PROVIDER) return true;
  return nodeEnv !== "production" || allowMock === "true";
}

export function isPaymentProviderAllowed(provider: string): boolean {
  return isPaymentProviderAllowedFor({
    provider,
    nodeEnv: process.env.NODE_ENV,
    allowMock: process.env.NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS,
  });
}
