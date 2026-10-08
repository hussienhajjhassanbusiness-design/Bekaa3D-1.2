import { NotFoundContent } from "@/components/feedback/NotFoundContent";
import { OrderLineItem } from "./OrderLineItem";
import { OrderSummaryDisplay } from "./OrderSummaryDisplay";
import type { OrderDetailModel } from "@/lib/orders/orderModel";

export type { OrderDetailModel };

// Deliberately NO "forbidden"/"forbidden-foreign" variant — a
// structural guarantee that no consumer could render a distinct
// "you don't own this order" message even by mistake
// (#SECURITY-ORDER-IDOR-HIDING).
export type OrderDetailLoadResult = { kind: "loaded"; order: OrderDetailModel } | { kind: "not-found" };

export interface OrderDetailProps {
  result: OrderDetailLoadResult;
}

// #SECURITY-ORDER-IDOR-HIDING, #ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE
//
// A foreign order and a nonexistent order both reduce to
// {kind:"not-found"} before reaching this component, which renders
// the exact same NotFoundContent the app's global 404 uses — never a
// distinct "forbidden" message. The "loaded" branch renders only
// confirmed-concept summary fields when present on the model, never
// fabricating a section for an absent one, and never performs a
// current-catalogue fetch.
export function OrderDetail({ result }: OrderDetailProps) {
  if (result.kind === "not-found") {
    return <NotFoundContent />;
  }

  const { order } = result;

  return (
    <div className="flex flex-col gap-6 tablet:flex-row-reverse tablet:items-start">
      <div className="tablet:w-64 tablet:shrink-0">
        <h2 className="text-h3 font-bold text-text-primary">Order {order.id}</h2>
        <p className="text-caption text-text-secondary">{order.displayDate}</p>
        <div className="mt-4">
          <OrderSummaryDisplay summary={order.summary} />
        </div>
      </div>

      <ul className="flex-1">
        {order.lines.map((line) => (
          <li key={line.id}>
            <OrderLineItem line={line} />
          </li>
        ))}
      </ul>
    </div>
  );
}
