import { useEffect } from "react";
import { hasPendingAssetFiles, type AssetFile } from "./assetVersionWorkflow";

export interface UseScanStatusPollingOptions {
  files: readonly AssetFile[];
  // REQUIRED — never a built-in default. "Scan should be done by now"
  // is never inferred from elapsed client time
  // (FVS-018-IMPLEMENTATION-PLAN.md §1); a confirmed interval comes
  // from the backend/product contract once it exists.
  intervalMs: number;
  onPoll: () => void;
}

// #ARCHITECTURE-SCAN-POLLING
//
// Contract-independent: this hook only decides WHETHER to keep polling
// (any file still "pending") — what `onPoll` actually does (a future
// TanStack Query refetch, once the real list/detail endpoint exists)
// is entirely the caller's concern, not this hook's. No WebSocket/SSE
// — polling only, matching VS-016's own confirmed "no push mechanism"
// architecture. Stops as soon as no file is pending (clean/infected are
// both terminal) and always cleans up on unmount or interval change.
export function useScanStatusPolling({ files, intervalMs, onPoll }: UseScanStatusPollingOptions): void {
  const isPending = hasPendingAssetFiles(files);

  useEffect(() => {
    if (!isPending) {
      return;
    }
    const id = setInterval(onPoll, intervalMs);
    return () => clearInterval(id);
  }, [isPending, intervalMs, onPoll]);
}
