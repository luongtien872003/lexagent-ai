import type { Citation } from "@/lib/types";
import { IconExternalLink } from "@/components/ui/icons";

const CITE_STYLES: Record<Citation["color"], { base: string; active: string }> = {
  amber:  {
    base:   "border-cite-amber-line  bg-cite-amber  text-cite-amber-text",
    active: "border-gold-border      bg-gold-dim     text-gold",
  },
  green:  {
    base:   "border-cite-green-line  bg-cite-green  text-cite-green-text",
    active: "border-cite-green-line  bg-cite-green  text-cite-green-text opacity-100",
  },
  blue:   {
    base:   "border-cite-blue-line   bg-cite-blue   text-cite-blue-text",
    active: "border-cite-blue-line   bg-cite-blue   text-cite-blue-text  opacity-100",
  },
  purple: {
    base:   "border-cite-purple-line bg-cite-purple text-cite-purple-text",
    active: "border-cite-purple-line bg-cite-purple text-cite-purple-text opacity-100",
  },
};

interface CitationChipProps {
  citation:    Citation;
  isActive:    boolean;
  isHovered?:  boolean;
  onClick:     () => void;
  onMouseEnter?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  onMouseLeave?: () => void;
}

/**
 * CitationChip — bottom-of-message citation reference pill.
 *
 * Design evolution from original:
 * - Removed the monospace number badge — redundant with the superscript in inline cite
 * - Compact: shows "§38" article number + short title fragment
 * - Icon only appears on hover (reduces visual noise at rest)
 * - Active state: gold accent regardless of citation color
 *   (consistent visual language with the source panel's active state)
 * - Hover: slight scale + opacity boost
 *
 * The chip is secondary to the inline reference. It exists for quick
 * re-access, not as the primary navigation element.
 */
export default function CitationChip({
  citation,
  isActive,
  isHovered = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: CitationChipProps) {
  const s = CITE_STYLES[citation.color];
  const articleNum = citation.id.replace("d", "");

  // Short label: "Điều 38 — Quyền..." → just the title part, truncated
  const titlePart = citation.label.split(" — ")[1] ?? "";
  const shortTitle = titlePart.length > 28
    ? titlePart.slice(0, 28).trimEnd() + "…"
    : titlePart;

  return (
    <button
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={[
        "group inline-flex items-center gap-1.5",
        "rounded-md border pl-2.5 pr-2.5 py-[7px]",
        "text-xs leading-none",
        "transition-all duration-150",
        isActive
          ? `${s.active} scale-[1.01] shadow-[0_0_0_2px_rgba(184,144,106,0.10)]`
          : isHovered
            ? `${s.base} opacity-100 scale-[1.01]`
            : `${s.base} opacity-70 hover:opacity-100`,
      ].join(" ")}
    >
      {/* Article number */}
      <span className="font-mono text-[10px] tracking-[0.02em] opacity-75">
        Đ{articleNum}
      </span>

      {/* Separator */}
      <span className="opacity-25">·</span>

      {/* Short title */}
      <span className="font-medium leading-none truncate max-w-[160px]">
        {shortTitle}
      </span>

      {/* External link icon — only on hover/active */}
      <IconExternalLink
        className={[
          "w-[9px] h-[9px] flex-shrink-0 ml-px",
          "transition-opacity duration-150",
          isActive || isHovered ? "opacity-50" : "opacity-0 group-hover:opacity-40",
        ].join(" ")}
      />
    </button>
  );
}
