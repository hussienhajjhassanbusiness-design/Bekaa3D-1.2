// The single place the browser leaves for the payment provider's page.
// The URL is the server's `payment.redirect_url`, followed exactly as
// given (checkoutModel.isFollowableRedirect has already refused anything
// that is not absolute http(s)). Kept in its own module so tests can
// observe the navigation without performing it.
export function followPaymentRedirect(url: string): void {
  window.location.assign(url);
}
