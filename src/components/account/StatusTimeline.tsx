export interface StatusTimelineEntry {
  label: string;
  timeLabel?: string;
  isCurrent?: boolean;
  isCompleted?: boolean;
}

export interface StatusTimelineProps {
  entries: readonly StatusTimelineEntry[];
}

// #FVS029 — fully caller-supplied. This component never encodes a
// fulfillment state machine itself, and never invents
// paid/production/printing/delivery/delivered as a canonical graph.
// Current/completed presentation is always paired with visible text,
// never color alone.
//
// Batch 7 (Stitch §45 activity feed): an ordered list with a decorative
// dot + connector rail, the entry's label in body text and its time in the
// mono caption role. The rail is decoration only; the list order and the
// text carry the meaning.
export function StatusTimeline({ entries }: StatusTimelineProps) {
  return (
    <ol className="flex flex-col">
      {entries.map((entry, index) => (
        <li key={index} className="relative flex gap-4 pb-5 last:pb-0">
          <span aria-hidden="true" className="relative flex w-3 shrink-0 justify-center">
            <span
              className={`mt-1.5 h-3 w-3 rounded-full border-2 ${
                entry.isCurrent ? "border-primary bg-primary" : "border-primary/60 bg-surface-container-lowest"
              }`}
            />
            {index < entries.length - 1 && (
              <span className="absolute bottom-[-1.25rem] top-5 w-0.5 bg-outline-variant/50" />
            )}
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5 tablet:flex-row tablet:items-baseline tablet:justify-between tablet:gap-4">
            <span className="min-w-0 break-words text-body-md text-on-surface">
              {entry.label}
              {entry.isCurrent && <span className="ml-2 text-body text-on-surface-variant">(Current)</span>}
              {entry.isCompleted && <span className="ml-2 text-body text-on-surface-variant">(Completed)</span>}
            </span>
            {entry.timeLabel && (
              <span className="shrink-0 font-label text-label-caps uppercase text-on-surface-variant">
                {entry.timeLabel}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
