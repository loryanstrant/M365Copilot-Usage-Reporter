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
  const parsed = new Date(date);
  const day = Number.isNaN(parsed.getTime())
    ? date
    : parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
  return `built ${day}${time ? ` at ${time}` : ""}`;
}
