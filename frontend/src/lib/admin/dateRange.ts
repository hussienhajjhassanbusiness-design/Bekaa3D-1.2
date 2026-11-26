// #ADMIN-DATE-RANGE (phase 6A)
//
// Turns the admin lists' <input type="date"> values into the aware ISO
// instants the backend's date filters require (a naive datetime is a 422).
// Dates are the administrator's local days. "From" is local midnight of
// that day (inclusive); "to" is local midnight of the FOLLOWING day, so the
// whole chosen day is included under the backend's exclusive upper bound.
// An empty or malformed value is omitted, never guessed.
const DATE = /^\d{4}-\d{2}-\d{2}$/;

function localMidnight(value: string, addDays = 0): string | undefined {
  if (!DATE.test(value)) return undefined;
  const [y, m, d] = value.split("-").map(Number) as [number, number, number];
  const date = new Date(y, m - 1, d + addDays, 0, 0, 0, 0);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export function dayStart(value: string): string | undefined {
  return localMidnight(value);
}

export function dayEndExclusive(value: string): string | undefined {
  return localMidnight(value, 1);
}
