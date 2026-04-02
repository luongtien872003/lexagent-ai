"use client";

import { useState, useCallback, useRef } from "react";
import type { CitationHoverState } from "@/lib/types";

// BUG FIXED: Previous version only exported onCiteEnter/onCiteLeave.
// The tooltip's own onMouseEnter was a no-op comment in ChatWindow.tsx.
// This meant: hovering citation (timer starts) → cursor moves to tooltip
// → 120ms later tooltip closes. Every time.
//
// Fix: export a `cancelLeave` function that the tooltip's onMouseEnter calls
// directly. This cancels the pending leave timer without needing to re-trigger
// a full enter (which would re-start the 160ms enter delay and flash the tooltip).

const ENTER_DELAY = 160;
const LEAVE_DELAY = 120;

interface UseCitationHoverReturn {
  hoverState:   CitationHoverState;
  onCiteEnter:  (id: string, rect: DOMRect) => void;
  onCiteLeave:  () => void;
  cancelLeave:  () => void;  // for tooltip's onMouseEnter
}

export function useCitationHover(): UseCitationHoverReturn {
  const [hoverState, setHoverState] = useState<CitationHoverState>({
    id:         null,
    anchorRect: null,
  });

  const enterTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelLeave = useCallback(() => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current);
  }, []);

  const onCiteEnter = useCallback((id: string, rect: DOMRect) => {
    cancelLeave();
    enterTimer.current = setTimeout(() => {
      setHoverState({ id, anchorRect: rect });
    }, ENTER_DELAY);
  }, [cancelLeave]);

  const onCiteLeave = useCallback(() => {
    if (enterTimer.current) clearTimeout(enterTimer.current);
    leaveTimer.current = setTimeout(() => {
      setHoverState({ id: null, anchorRect: null });
    }, LEAVE_DELAY);
  }, []);

  return { hoverState, onCiteEnter, onCiteLeave, cancelLeave };
}
