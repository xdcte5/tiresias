// Categorical color assignment — FIXED order, never cycled (dataviz non-negotiable).
// Exactly one validated palette slot per class; the anomalous "unclassified" bucket
// uses a neutral muted ink, never a categorical slot.

// Fixed class -> palette-slot order. Colors themselves live as CSS variables in
// theme.css so light/dark swap in one place; here we map a label to its var name.
export const CLASS_ORDER: string[] = [
  "video_streaming", // slot 1 blue
  "video_conferencing", // slot 2 aqua
  "web_browsing", // slot 3 yellow
  "file_transfer", // slot 4 green
  "gaming", // slot 5 violet
  "music_streaming", // slot 6 red
  "vpn", // slot 7 magenta
  "dns_background", // slot 8 orange
];

export const UNCLASSIFIED = "unclassified";

export function colorVar(label: string): string {
  if (label === UNCLASSIFIED) return "var(--muted)";
  return `var(--c-${label})`;
}

// Order an arbitrary set of labels by the fixed categorical order (unknowns last).
export function orderClasses(labels: string[]): string[] {
  const known = CLASS_ORDER.filter((c) => labels.includes(c));
  const extra = labels.filter((c) => !CLASS_ORDER.includes(c) && c !== UNCLASSIFIED).sort();
  return [...known, ...extra];
}

export function prettyLabel(label: string): string {
  return label
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
