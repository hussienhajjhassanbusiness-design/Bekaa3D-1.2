"use client";

import { Button } from "@/components/forms/Button";

export interface LoadMoreProps {
  hasMore: boolean;
  onLoadMore: () => void;
  isLoading?: boolean;
}

// Cursor pagination means no numbered page picker
// (FVS-013-IMPLEMENTATION-PLAN.md §0) — this is the only pagination
// control the catalogue renders. It never interprets, decodes, or
// constructs a cursor; `hasMore` is fully parent-controlled from
// whatever the real list response eventually says.
export function LoadMore({ hasMore, onLoadMore, isLoading = false }: LoadMoreProps) {
  if (!hasMore) {
    return null;
  }

  return (
    // Batch 3: Stitch places paging `mt-12`/`mt-16`, centred; cursor
    // paging has no page numbers (COMPONENT-MIGRATION "LoadMore"), so it is
    // one outline button.
    <div className="mt-12 flex justify-center">
      <Button type="button" variant="outline" onClick={onLoadMore} disabled={isLoading} isLoading={isLoading}>
        Load more
      </Button>
    </div>
  );
}
