/**
 * Formats an ISO-8601 timestamp as a Vietnamese relative date string.
 * "2 phút trước", "3 giờ trước", "hôm qua", "25/03"
 */
export function formatRelativeDate(iso: string): string {
  const now   = Date.now();
  const then  = new Date(iso).getTime();
  const diffMs = now - then;

  const minutes = Math.floor(diffMs / 60_000);
  const hours   = Math.floor(diffMs / 3_600_000);
  const days    = Math.floor(diffMs / 86_400_000);

  if (minutes < 1)  return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  if (hours   < 24) return `${hours} giờ trước`;
  if (days    < 2)  return "Hôm qua";

  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Converts an internal article ID to its display label.
 * "d38" → "Điều 38", "d155" → "Điều 155"
 */
export function formatArticleId(id: string): string {
  return id.replace(/^d(\d+)$/, "Điều $1");
}

/**
 * Returns true if the timestamp is from today.
 */
export function isToday(iso: string): boolean {
  const d    = new Date(iso);
  const now  = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth()    === now.getMonth()    &&
    d.getDate()     === now.getDate()
  );
}
