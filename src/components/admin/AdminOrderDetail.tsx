import { AdminOrderSummaryDisplay } from "./AdminOrderSummaryDisplay";
import { InternalNoteEditor } from "./InternalNoteEditor";
import { AdminOrderLine } from "./AdminOrderLine";
import type { AdminOrderModel } from "@/lib/admin/adminOrderModel";

export interface AdminOrderDetailProps {
  order: AdminOrderModel;
  pendingActionId?: string | null;
  onSelectAction: (lineId: string, actionId: string) => void;
  onSaveNote: (note: string) => void;
  isSavingNote?: boolean;
  noteErrorMessage?: string;
}

// #ARCHITECTURE-ADMIN-ORDER-PROJECTION
//
// Composes FVS-029's AdminOrderSummaryDisplay unmodified (AdminOrderModel
// reuses OrderSummaryModel verbatim, so no payment-provider secret or
// raw payload prop exists on this component structurally) alongside
// InternalNoteEditor and one AdminOrderLine per order line.
export function AdminOrderDetail({
  order,
  pendingActionId,
  onSelectAction,
  onSaveNote,
  isSavingNote,
  noteErrorMessage,
}: AdminOrderDetailProps) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-h3 font-bold text-text-primary">Order {order.id}</h2>
        <p className="text-caption text-text-secondary">{order.displayDate}</p>
        <div className="mt-4">
          <AdminOrderSummaryDisplay summary={order.summary} />
        </div>
      </div>

      <InternalNoteEditor
        note={order.internalNote}
        onSave={onSaveNote}
        isSaving={isSavingNote}
        errorMessage={noteErrorMessage}
      />

      <ul className="flex flex-col gap-4">
        {order.lines.map((line) => (
          <li key={line.id}>
            <AdminOrderLine line={line} pendingActionId={pendingActionId} onSelectAction={onSelectAction} />
          </li>
        ))}
      </ul>
    </div>
  );
}
