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
export function StatusTimeline({ entries }: StatusTimelineProps) {
  return (
    <ol className="flex flex-col gap-2">
      {entries.map((entry, index) => (
        <li key={index} className="flex items-center justify-between gap-2 text-body text-text-primary">
          <span>
            {entry.label}
            {entry.isCurrent && <span className="ml-2 text-caption text-text-secondary">(Current)</span>}
            {entry.isCompleted && <span className="ml-2 text-caption text-text-secondary">(Completed)</span>}
          </span>
          {entry.timeLabel && <span className="text-caption text-text-secondary">{entry.timeLabel}</span>}
        </li>
      ))}
    </ol>
  );
}
