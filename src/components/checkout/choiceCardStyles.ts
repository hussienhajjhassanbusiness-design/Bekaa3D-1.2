// Redesign Batch 6 — the checkout choice card (COMPONENT-SPECS §28 radio
// card / §34 payment option card). The native radio stays visible and is
// the control (keyboard, group semantics, accessible name from the
// wrapping <label>); the card only reacts to its state with :has(). The
// selected state is a primary border + ring + tint AND the checked radio,
// never colour alone. A disabled option keeps fully legible text on a
// tinted surface (no opacity fade).
export const CHOICE_CARD_CLASSES =
  "flex min-w-0 cursor-pointer items-start gap-4 rounded-card border border-outline-variant bg-surface-container-lowest p-4 tablet:p-5 " +
  "transition-colors duration-200 ease-standard motion-reduce:transition-none " +
  "hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:checked]:ring-1 has-[:checked]:ring-primary " +
  "has-[:disabled]:cursor-not-allowed has-[:disabled]:bg-surface-container-low has-[:disabled]:hover:border-outline-variant";

export const CHOICE_INPUT_CLASSES = "mt-0.5 h-5 w-5 shrink-0 cursor-[inherit] accent-primary";

export const CHOICE_TITLE_CLASSES = "block font-headline text-title-sm text-on-surface";

export const CHOICE_HINT_CLASSES = "mt-1 block text-caption text-on-surface-variant";

export const STEP_CARD_CLASSES =
  "min-w-0 rounded-card border border-outline-variant/30 bg-surface-container-lowest p-5 shadow-sm tablet:p-8";

export const FIELD_ERROR_CLASSES = "mt-2 flex items-start gap-1.5 text-caption text-error";
