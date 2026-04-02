"use client";

// BUG FIXED: The previous version used `position: absolute` with `window.scrollY` offsets
// on an element portaled to document.body. This is wrong. A portaled element's
// offsetParent is the body, so `position: absolute` behaves like `position: fixed`
// for transforms, but the `top` value was `anchorRect.bottom + window.scrollY`, which
// means it scrolls WITH the page. Correct approach: position: fixed, use raw
// getBoundingClientRect() values directly (they are already viewport-relative).
//
// BUG FIXED: `bottom: \`calc(100vh - ${...}px + ${TOOLTIP_OFFSET}px)\`` was a
// template literal string in a React style object. React passes this verbatim as
// an inline style. CSS calc() works in inline styles, but `100vh` inside
// position:absolute calc() was being calculated against the wrong stacking context.
// With position:fixed, just use `top = anchorRect.top - TOOLTIP_HEIGHT - TOOLTIP_OFFSET`.
//
// BUG FIXED: The `onMouseEnter` in ChatWindow was a no-op comment that said
// "keep tooltip open". This meant moving the cursor FROM the citation TO the tooltip
// would always close the tooltip after 120ms. The fix: accept a `onTooltipEnter`
// and `onTooltipLeave` prop that are passed from useCitationHover.

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Citation, DieuRecord } from "@/lib/types";

interface CitationTooltipProps {
  citation:       Citation | null;
  anchorRect:     DOMRect | null;
  record:         DieuRecord | null;
  onTooltipEnter: () => void;
  onTooltipLeave: () => void;
  onCiteClick?:   (id: string) => void;  // open sidebar on click
}

const TOOLTIP_WIDTH  = 300;
const TOOLTIP_OFFSET = 8;
const VIEWPORT_PAD   = 14;

export default function CitationTooltip({
  citation,
  anchorRect,
  record,
  onTooltipEnter,
  onTooltipLeave,
  onCiteClick,
}: CitationTooltipProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted || !citation || !anchorRect) return null;

  // ── Fixed positioning — coordinates are already viewport-relative ────
  const viewportH = window.innerHeight;
  const viewportW = window.innerWidth;

  // Prefer above; flip below when anchor is in top third
  const showBelow = anchorRect.top < viewportH * 0.35;

  const top = showBelow
    ? anchorRect.bottom + TOOLTIP_OFFSET
    : anchorRect.top - TOOLTIP_OFFSET - 200; // approximate; CSS handles overflow

  let left = anchorRect.left + anchorRect.width / 2 - TOOLTIP_WIDTH / 2;
  left = Math.max(VIEWPORT_PAD, Math.min(left, viewportW - TOOLTIP_WIDTH - VIEWPORT_PAD));

  const articleNum   = citation.id.replace("d", "");
  const title        = record?.title ?? citation.label.split(" — ")[1] ?? "";
  const chuong       = citation.chuong_label ?? record?.chuong ?? "";
  const snippetRaw   = citation.snippet ?? record?.khoans[0]?.text ?? "";
  const snippet      = snippetRaw.length > 200
    ? snippetRaw.slice(0, 200).trimEnd() + "…"
    : snippetRaw;

  const tooltip = (
    <div
      onMouseEnter={onTooltipEnter}
      onMouseLeave={onTooltipLeave}
      style={{
        position:      "fixed",
        top,
        left,
        width:         TOOLTIP_WIDTH,
        zIndex:        9998,
        pointerEvents: "auto",
        animation:     "tooltipIn 130ms cubic-bezier(0.16,1,0.3,1) both",
      }}
    >
      <style>{`
        @keyframes tooltipIn {
          from { opacity: 0; transform: translateY(${showBelow ? "-4px" : "4px"}); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{
        background:    "#17171a",
        border:        "1px solid rgba(255,255,255,0.09)",
        borderRadius:  "8px",
        boxShadow:     "0 8px 28px rgba(0,0,0,0.45), 0 1px 0 rgba(255,255,255,0.04) inset",
        padding:       "13px 15px 14px",
      }}>
        {/* Article num + chapter */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginBottom: "6px" }}>
          <span style={{
            fontFamily:    "'Lora', Georgia, serif",
            fontSize:      "17px",
            fontStyle:     "italic",
            color:         "#b8906a",
            lineHeight:    1,
          }}>
            Điều {articleNum}
          </span>
          {chuong && (
            <span style={{
              fontFamily:    "'JetBrains Mono', 'Courier New', monospace",
              fontSize:      "9.5px",
              letterSpacing: "0.07em",
              textTransform: "uppercase" as const,
              color:         "#303038",
            }}>
              {chuong}
            </span>
          )}
        </div>

        {/* Title */}
        {title && (
          <p style={{
            fontSize:   "12px",
            fontWeight: 500,
            color:      "#e8e8ea",
            lineHeight: 1.5,
            margin:     "0 0 8px",
          }}>
            {title}
          </p>
        )}

        {/* Snippet */}
        {snippet && (
          <p style={{
            fontSize:    "11.5px",
            color:       "#52525e",
            lineHeight:  1.6,
            borderTop:   "1px solid rgba(255,255,255,0.048)",
            paddingTop:  "8px",
            margin:      0,
          }}>
            {snippet}
          </p>
        )}

        {/* Hint — clickable to open sidebar */}
        <button
          onClick={() => citation && onCiteClick?.(citation.id)}
          style={{
            marginTop:     "10px",
            display:       "block",
            width:         "100%",
            textAlign:     "left",
            background:    "none",
            border:        "none",
            padding:       0,
            cursor:        onCiteClick ? "pointer" : "default",
            fontFamily:    "'JetBrains Mono', 'Courier New', monospace",
            fontSize:      "9px",
            letterSpacing: "0.05em",
            textTransform: "uppercase" as const,
            color:         onCiteClick ? "#b8906a" : "#303038",
            transition:    "color 150ms",
          }}
          onMouseEnter={e => { if (onCiteClick) (e.target as HTMLElement).style.color = "#c49870"; }}
          onMouseLeave={e => { if (onCiteClick) (e.target as HTMLElement).style.color = "#b8906a"; }}
        >
          Nhấn để xem đầy đủ →
        </button>
      </div>
    </div>
  );

  return createPortal(tooltip, document.body);
}
