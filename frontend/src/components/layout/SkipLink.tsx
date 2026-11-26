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
      // Batch 3: a solid primary chip (white on #0d631b, 7.45:1) pinned top
      // left above the sticky header (z-60 > header 40 > sheets 50), with a
      // 44px target. Hidden until focused, exactly as before.
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[60] focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-control focus:bg-primary focus:px-5 focus:py-3 focus:font-label focus:text-label-caps focus:uppercase focus:text-on-primary focus:shadow-xl"
    >
      Skip to main content
    </a>
  );
}
