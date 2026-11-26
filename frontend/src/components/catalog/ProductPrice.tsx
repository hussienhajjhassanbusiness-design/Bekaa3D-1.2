import { PriceDisplay } from "./PriceDisplay";
import type { ProductCardModel } from "@/lib/catalog/productAdapters";

export interface ProductPriceProps {
  price: ProductCardModel["price"];
  promotion: ProductCardModel["promotion"];
  size: "card" | "detail";
}

// #SHARED-PRODUCT-PRICE (Stitch COMPONENT-SPECS §17 "Discount pair" / "Detail
// hero"): the server's current price, and — only while the server reports a
// promotion — its own list price struck through beside it. Both amounts are
// the server's fields, never a computation. The difference is never carried
// by colour or the strike alone: screen readers hear "Current promotional
// price … Original price …".
export function ProductPrice({ price, promotion, size }: ProductPriceProps) {
  if (!promotion) {
    return <PriceDisplay amountCents={price.amountCents} currency={price.currency} size={size} />;
  }
  const original =
    size === "detail" ? "font-headline text-headline-md text-on-surface-variant" : "text-xs text-on-surface-variant";
  return (
    <p className={`flex flex-wrap items-baseline ${size === "detail" ? "gap-4" : "gap-2"}`}>
      <span>
        <span className="sr-only">Current promotional price: </span>
        <PriceDisplay amountCents={price.amountCents} currency={price.currency} size={size} />
      </span>
      <s className={`${original} tabular-nums decoration-1`}>
        <span className="sr-only">Original price: </span>
        <PriceDisplay amountCents={promotion.listPrice.amountCents} currency={promotion.listPrice.currency} />
      </s>
    </p>
  );
}
