"use client";

// A same-page fragment link does not reliably move keyboard focus to its
// target in every browser — some engines only scroll to it. The explicit
// focus() call here guarantees focus transfer regardless of that browser
// inconsistency; native hash navigation/scrolling still happens as normal.
export function SkipLink() {
  function handleClick() {
    document.getElementById("main-content")?.focus();
  }

  return (
    <a
      href="#main-content"
      onClick={handleClick}
      className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface-base focus:px-4 focus:py-2 focus:text-text-primary focus:shadow-elevation-2"
    >
      Skip to main content
    </a>
  );
}
