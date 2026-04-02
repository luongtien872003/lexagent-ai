"use client";

import { useMemo } from "react";
import CitationChip from "./CitationChip";
import type {
  StructuredAnswer,
  AnswerSection,
  Citation,
  CitationColor,
  CitationHoverState,
} from "@/lib/types";

const CITE_STYLES: Record<CitationColor, { pill: string }> = {
  amber:  { pill: "bg-cite-amber  text-cite-amber-text  border-cite-amber-line"  },
  green:  { pill: "bg-cite-green  text-cite-green-text  border-cite-green-line"  },
  blue:   { pill: "bg-cite-blue   text-cite-blue-text   border-cite-blue-line"   },
  purple: { pill: "bg-cite-purple text-cite-purple-text border-cite-purple-line" },
};

// ── Summary ────────────────────────────────────────────────────────────────
// DEMO TELL REMOVED: "Dựa trên N điều luật" subtitle was patronizing and
// redundant — the citations are visible right below. Removed entirely.
//
// LAYOUT SHIFT FIXED: The summary previously used `borderLeft: "2px solid ..."` as
// an inline style applied to a div. The 2px left border adds to the element's box
// model, shifting content 2px right on every render. Fixed by using a pseudo-element
// approach via a positioned left-rail div instead of a border.

function SummaryBlock({ summary }: { summary: string }) {
  if (!summary) return null;

  return (
    <div
      className="pl-4 mb-7 animate-fade-up relative"
      style={{ animationDuration: "280ms" }}
    >
      {/* Left rail — positioned, not a border, so zero layout shift */}
      <div
        className="absolute left-0 top-[3px] bottom-[3px] w-[2px] rounded-full"
        style={{ background: "rgba(184,144,106,0.35)" }}
      />
      <p className="font-serif text-[16px] text-ink-0 leading-[1.82] tracking-[-0.01em] italic">
        {summary}
      </p>
    </div>
  );
}

// ── Inline citation reference ──────────────────────────────────────────────

function InlineCiteRef({
  citation,
  isActive,
  isHovered,
  onCiteClick,
  onCiteEnter,
  onCiteLeave,
}: {
  citation:    Citation;
  isActive:    boolean;
  isHovered:   boolean;
  onCiteClick: (id: string) => void;
  onCiteEnter: (id: string, rect: DOMRect) => void;
  onCiteLeave: () => void;
}) {
  const s          = CITE_STYLES[citation.color];
  const articleNum = citation.id.replace("d", "");

  return (
    <button
      onClick={() => onCiteClick(citation.id)}
      onMouseEnter={e => onCiteEnter(citation.id, e.currentTarget.getBoundingClientRect())}
      onMouseLeave={onCiteLeave}
      title={citation.label}
      className={[
        // inline-flex keeps the pill + bracket as one unit, no overflow
        "inline-flex items-center",
        "font-mono text-[10px] px-[5px] py-[2px]",
        "rounded-sm border",
        "transition-all duration-150 cursor-pointer",
        // vertical-align: middle keeps it on the text baseline, no jump
        "align-middle mx-[2px]",
        isActive
          ? "border-gold-border bg-gold-dim text-gold scale-105 shadow-[0_0_0_2px_rgba(184,144,106,0.12)]"
          : isHovered
            ? `${s.pill} opacity-100 scale-[1.03]`
            : `${s.pill} opacity-80 hover:opacity-100`,
      ].join(" ")}
    >
      [{articleNum}]
    </button>
  );
}

// ── Section block ──────────────────────────────────────────────────────────

function SectionBlock({
  section,
  sectionIdx,
  sectionCitations,
  activeCiteId,
  hoverState,
  onCiteClick,
  onCiteEnter,
  onCiteLeave,
}: {
  section:          AnswerSection;
  sectionIdx:       number;
  sectionCitations: Citation[];
  activeCiteId:     string | null;
  hoverState:       CitationHoverState;
  onCiteClick:      (id: string) => void;
  onCiteEnter:      (id: string, rect: DOMRect) => void;
  onCiteLeave:      () => void;
}) {
  return (
    <div
      className="mb-7 last:mb-0 animate-fade-up"
      style={{
        animationDelay:    `${sectionIdx * 80}ms`,
        animationDuration: "260ms",
        animationFillMode: "both",
      }}
    >
      {/* Section label row */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[11px] font-medium text-ink-2 leading-none whitespace-nowrap">
          {section.title}
        </span>
        <span className="flex-1 h-px bg-line" />
        <div className="flex items-center gap-1">
          {sectionCitations.map(cit => (
            <InlineCiteRef
              key={cit.id}
              citation={cit}
              isActive={activeCiteId === cit.id}
              isHovered={hoverState.id === cit.id}
              onCiteClick={onCiteClick}
              onCiteEnter={onCiteEnter}
              onCiteLeave={onCiteLeave}
            />
          ))}
        </div>
      </div>

      {/* Bullets */}
      <ul className="space-y-[10px]">
        {section.bullets.map((bullet, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="w-[3px] h-[3px] rounded-full bg-ink-3 flex-shrink-0 mt-[9px] opacity-50" />
            <span className="text-body text-ink-0 leading-[1.80]">{bullet}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Main export ────────────────────────────────────────────────────────────

interface StructuredAnswerProps {
  structured:   StructuredAnswer;
  citations:    Citation[];
  activeCiteId: string | null;
  hoverState:   CitationHoverState;
  onCiteClick:  (id: string) => void;
  onCiteEnter:  (id: string, rect: DOMRect) => void;
  onCiteLeave:  () => void;
}

export default function StructuredAnswerComponent({
  structured,
  citations,
  activeCiteId,
  hoverState,
  onCiteClick,
  onCiteEnter,
  onCiteLeave,
}: StructuredAnswerProps) {
  const citeLookup = useMemo(() => {
    const map = new Map<number, Citation>();
    for (const cit of citations) {
      const n = parseInt(cit.id.slice(1), 10);
      if (!isNaN(n)) map.set(n, cit);
    }
    return map;
  }, [citations]);

  const usedInSections = useMemo(() => {
    const ids = new Set<string>();
    for (const sec of structured.sections) {
      for (const id of sec.citation_ids) {
        const cit = citeLookup.get(id);
        if (cit) ids.add(cit.id);
      }
    }
    return ids;
  }, [structured.sections, citeLookup]);

  const footerCitations = citations.filter(c => !usedInSections.has(c.id));

  return (
    <div>
      <SummaryBlock summary={structured.summary} />

      {structured.sections.length > 0 && (
        <div>
          {structured.sections.map((section, i) => {
            const sectionCites = section.citation_ids
              .map(id => citeLookup.get(id))
              .filter((c): c is Citation => c !== undefined);
            return (
              <SectionBlock
                key={i}
                section={section}
                sectionIdx={i}
                sectionCitations={sectionCites}
                activeCiteId={activeCiteId}
                hoverState={hoverState}
                onCiteClick={onCiteClick}
                onCiteEnter={onCiteEnter}
                onCiteLeave={onCiteLeave}
              />
            );
          })}
        </div>
      )}

      {footerCitations.length > 0 && (
        <div
          className="flex flex-wrap gap-1.5 mt-5 pt-4 border-t border-line animate-fade-up"
          style={{ animationDelay: `${structured.sections.length * 80 + 40}ms`, animationFillMode: "both" }}
        >
          {footerCitations.map(cit => (
            <CitationChip
              key={cit.id}
              citation={cit}
              isActive={activeCiteId === cit.id}
              isHovered={hoverState.id === cit.id}
              onClick={() => onCiteClick(cit.id)}
              onMouseEnter={e => onCiteEnter(cit.id, e.currentTarget.getBoundingClientRect())}
              onMouseLeave={onCiteLeave}
            />
          ))}
        </div>
      )}
    </div>
  );
}
