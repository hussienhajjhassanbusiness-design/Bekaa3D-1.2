import Link from "next/link";

export interface CheckoutLineIssue {
  productId: string;
  name: string;
  // Already-safe frontend copy, completing the sentence after the name.
  detail?: string;
}

export interface CheckoutLineIssuesProps {
  message: string;
  items: readonly CheckoutLineIssue[];
  showCartLink?: boolean;
}

// #FVS026-LINE-ISSUES
//
// Names every line the server refused (PRODUCT_NOT_PURCHASABLE,
// QUANTITY_EXCEEDS_LIMIT, PRODUCT_ALREADY_OWNED), the lines the cart itself
// flags as not purchasable, and the already-owned STLs a CART_EMPTY or a
// placed order dropped. Never a single collapsed "checkout failed".
export function CheckoutLineIssues({ message, items, showCartLink = false }: CheckoutLineIssuesProps) {
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-md border border-warning bg-warning-bg p-4">
      <p className="text-body font-semibold text-text-primary">{message}</p>
      {items.length > 0 && (
        <ul className="ml-4 list-disc text-body text-text-primary">
          {items.map((item) => (
            <li key={item.productId}>
              <span className="font-semibold">{item.name}</span>
              {item.detail && <> {item.detail}</>}
            </li>
          ))}
        </ul>
      )}
      {showCartLink && (
        <Link href="/cart" className="self-start font-semibold text-brand-dark-green underline">
          Review your cart
        </Link>
      )}
    </div>
  );
}
