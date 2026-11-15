import Link from "next/link";
import { Icon } from "@/components/ui/Icon";

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
//
// Redesign Batch 6: warning card (icon + text), each line in its own row
// with the product name in bold.
export function CheckoutLineIssues({ message, items, showCartLink = false }: CheckoutLineIssuesProps) {
  return (
    <div
      role="alert"
      className="flex w-full flex-col gap-3 rounded-card border border-warning-outline bg-warning-container p-4 text-on-warning-container tablet:p-5"
    >
      <p className="flex items-start gap-3 text-sm font-semibold">
        <Icon name="warning" className="h-5 w-5" />
        <span className="min-w-0">{message}</span>
      </p>
      {items.length > 0 && (
        <ul className="flex flex-col divide-y divide-outline-variant/40 rounded-control border border-warning-outline bg-surface-container-lowest text-sm text-on-surface">
          {items.map((item) => (
            <li key={item.productId} className="break-words px-3 py-2.5">
              <span className="font-semibold">{item.name}</span>
              {item.detail && <> {item.detail}</>}
            </li>
          ))}
        </ul>
      )}
      {showCartLink && (
        <Link
          href="/cart"
          className="inline-flex min-h-11 items-center gap-2 self-start rounded-badge font-semibold text-primary underline decoration-1 underline-offset-4 hover:decoration-2"
        >
          Review your cart
          <Icon name="arrow-forward" className="h-4 w-4" />
        </Link>
      )}
    </div>
  );
}
