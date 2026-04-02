import type { Citation, ContentBlock, CitationHoverState } from "@/lib/types";

const CITE_STYLES: Record<Citation["color"], { pill: string }> = {
  amber:  { pill: "bg-cite-amber  text-cite-amber-text  border-cite-amber-line"  },
  green:  { pill: "bg-cite-green  text-cite-green-text  border-cite-green-line"  },
  blue:   { pill: "bg-cite-blue   text-cite-blue-text   border-cite-blue-line"   },
  purple: { pill: "bg-cite-purple text-cite-purple-text border-cite-purple-line" },
};

interface ContentRendererProps {
  blocks:       ContentBlock[];
  activeCiteId?: string | null;
  hoverState?:  CitationHoverState;
  onCiteClick?: (id: string) => void;
  onCiteEnter?: (id: string, rect: DOMRect) => void;
  onCiteLeave?: () => void;
}

/**
 * Renders flat ContentBlock[] for legacy messages without StructuredAnswer.
 *
 * CHANGES:
 * - activeCiteId prop: inline citation buttons highlight when their source panel is open
 * - hoverState prop: inline buttons respond to hover (synced with tooltip)
 * - Citation style: compact §NN format matching StructuredAnswer's InlineCiteRef
 * - onCiteEnter/Leave: tooltip trigger handlers
 */
export default function ContentRenderer({
  blocks,
  activeCiteId,
  hoverState,
  onCiteClick,
  onCiteEnter,
  onCiteLeave,
}: ContentRendererProps) {
  // Split blocks into paragraphs on "break" boundaries
  const paragraphs: ContentBlock[][] = [];
  let current: ContentBlock[] = [];

  for (const block of blocks) {
    if (block.type === "break") {
      if (current.length) { paragraphs.push(current); current = []; }
    } else {
      current.push(block);
    }
  }
  if (current.length) paragraphs.push(current);

  return (
    <>
      {paragraphs.map((para, i) => (
        <p key={i} className={i < paragraphs.length - 1 ? "mb-[18px]" : ""}>
          {para.map((block, j) => {
            if (block.type === "text") {
              return <span key={j}>{block.text}</span>;
            }

            if (block.type === "bold") {
              return (
                <strong key={j} className="font-medium text-ink-0">
                  {block.text}
                </strong>
              );
            }

            if (block.type === "cite") {
              const s           = CITE_STYLES[block.citation.color];
              const isActive    = activeCiteId === block.citation.id;
              const isHovered   = hoverState?.id === block.citation.id;
              const articleNum  = block.citation.id.replace("d", "");

              return (
                <button
                  key={j}
                  onClick={() => onCiteClick?.(block.citation.id)}
                  onMouseEnter={e => onCiteEnter?.(block.citation.id, e.currentTarget.getBoundingClientRect())}
                  onMouseLeave={onCiteLeave}
                  title={block.citation.label}
                  className={[
                    "inline-flex items-center gap-[2px]",
                    "font-mono text-[10.5px] px-[5px] py-[1.5px] mx-[2px]",
                    "rounded-xs border",
                    "transition-all duration-150 cursor-pointer",
                    "relative top-[-1px]",
                    isActive
                      ? "border-gold-border bg-gold-dim text-gold scale-105"
                      : isHovered
                        ? `${s.pill} opacity-100 scale-[1.03]`
                        : `${s.pill} opacity-75 hover:opacity-100`,
                  ].join(" ")}
                >
                  <sup className="text-[9px] font-mono tracking-tight leading-none mr-[1px]">[{articleNum}]</sup>
                </button>
              );
            }

            return null;
          })}
        </p>
      ))}
    </>
  );
}
