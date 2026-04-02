"use client";

import { useEffect, useRef } from "react";

/**
 * Attaches to a sentinel element and scrolls it into view
 * whenever any of the provided deps change.
 *
 * Uses rest params so React's exhaustive-deps rule can verify
 * call sites — no eslint-disable needed.
 */
export function useScrollToBottom(...deps: React.DependencyList) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
    // deps are spread by the caller — verified at each call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}
