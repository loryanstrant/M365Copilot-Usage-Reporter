/**
 * Which build is running, in words.
 *
 * Shown on the About page and, because knowing the answer is most useful when
 * you cannot get in to look, on the sign-in page too.
 *
 * No injected stamp means no build date. Saying "development build" is honest;
 * printing a made-up date is not.
 */
export function buildStamp(date: string | null, time: string | null): string {
  if (!date) return "development build";
  return `built ${formatDay(date)}${time ? ` at ${time}` : ""}`;
}

/**
 * Format a YYYY-MM-DD build date without moving it.
 *
 * `new Date("2026-09-29")` is parsed as UTC midnight, and `toLocaleDateString`
 * then renders it in the viewer's zone — so anyone west of UTC was shown the
 * day before the one the build actually happened on. A build stamp that is off
 * by a day is worse than no build stamp, because it is confidently wrong at
 * exactly the moment someone is using it to work out whether a deployment
 * landed.
 *
 * Splitting the parts and constructing a local date keeps the calendar day the
 * build server meant, in every zone.
 */
function formatDay(date: string): string {
  const parts = date.split("-").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return date;
  const [year, month, day] = parts;
  const local = new Date(year, month - 1, day);
  if (Number.isNaN(local.getTime())) return date;
  return local.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
