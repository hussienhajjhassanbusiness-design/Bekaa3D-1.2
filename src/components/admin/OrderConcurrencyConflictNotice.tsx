import { Button } from "@/components/forms/Button";

export interface OrderConcurrencyConflictNoticeProps {
  message: string;
  onRefresh: () => void;
}

// #SECURITY-ORDER-CONCURRENCY-REFETCH
//
// A generic conflict explanation with a refresh action — never an
// invented 409/412/version-mismatch code, and never a silent
// overwrite. The caller owns deciding when this renders and what
// `message` says; this component only presents it.
export function OrderConcurrencyConflictNotice({ message, onRefresh }: OrderConcurrencyConflictNoticeProps) {
  return (
    <div role="alert" className="flex items-center justify-between gap-4 rounded-md border border-danger p-4">
      <p className="text-body text-text-primary">{message}</p>
      <Button type="button" onClick={onRefresh}>
        Refresh
      </Button>
    </div>
  );
}
