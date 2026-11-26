import { useEffect, useState } from "react";

// Generic debounce — holds the previous value until `delayMs` has passed
// with no further change, then adopts the latest one. No business logic
// here (minimum length, trimming, etc. belong to the caller); this is a
// pure timing primitive reused by any future debounced-input feature, not
// just search suggestions.
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
