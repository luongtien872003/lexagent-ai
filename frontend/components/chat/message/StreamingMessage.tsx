"use client";

import { useRef, useMemo, useState, useEffect } from "react";
import AgentLabel from "./AgentLabel";
import type { PipelineStep, StreamPhase, AnswerSection, StepChild } from "@/lib/types";

// ── Timer ──────────────────────────────────────────────────────────────────────
function useElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (active) {
      startRef.current = Date.now();
      setElapsed(0);
      const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current!) / 1000)), 1000);
      return () => clearInterval(id);
    }
  }, [active]);
  return elapsed;
}

// ── Tree child row ─────────────────────────────────────────────────────────────
function ChildRow({ child, isLast }: { child: StepChild; isLast: boolean }) {
  const [open, setOpen] = useState(false);
  const hasMeta = !!(child.meta?.trim());
  const dotColor = child.done ? "rgba(74,153,102,0.6)" : "rgba(184,144,106,0.6)";

  return (
    <div className="flex" style={{ minHeight: 28 }}>
      <div className="flex-shrink-0 w-[20px] flex flex-col items-center">
        <div className="w-px bg-line-2" style={{ flex: "0 0 12px" }} />
        <div className="w-[5px] h-[5px] rounded-full flex-shrink-0"
          style={{ background: dotColor }} />
        {!isLast
          ? <div className="w-px bg-line-2 flex-1" />
          : <div style={{ flex: 1 }} />}
      </div>

      <div className="flex-1 min-w-0 pl-2 pb-1">
        <button
          onClick={() => hasMeta && setOpen(o => !o)}
          className="w-full text-left flex items-center gap-1.5 py-[3px]"
          style={{
            background: "none", border: "none",
            cursor: hasMeta ? "pointer" : "default", padding: "3px 0"
          }}
        >
          <span className="text-[11px] font-medium leading-snug flex-1"
            style={{ color: child.done ? "#5a5a6a" : "#b8906a" }}>
            {child.label}
          </span>
          {hasMeta && (
            <span className="text-[9px] flex-shrink-0 px-1.5 py-[1px] rounded"
              style={{
                color: "#52525e", background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.07)"
              }}>
              {open ? "ẩn" : "xem"}
            </span>
          )}
        </button>

        {hasMeta && open && (
          <div className="mt-1 ml-1 rounded"
            style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}>
            {child.meta!.split("\n").filter(Boolean).map((line, i, arr) => (
              <div key={i}
                className="flex items-baseline gap-1.5 px-2 py-[4px]"
                style={{ borderBottom: i < arr.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                <span className="font-mono text-[9px] flex-shrink-0" style={{ color: "#303038" }}>
                  {i + 1}
                </span>
                <p className="font-mono text-[10px] leading-[1.55]" style={{ color: "#6b6b7a" }}>
                  {line.replace(/^[•·]\s*/, "")}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Step line ──────────────────────────────────────────────────────────────────
function StepLine({ step }: { step: PipelineStep }) {
  const [metaOpen, setMetaOpen] = useState(false);
  const [childrenOpen, setChildrenOpen] = useState(true);
  const isActive = step.status === "active";
  const isDone = step.status === "done";
  const hasMeta = !!(step.meta?.trim());
  const hasChildren = (step.children?.length ?? 0) > 0;

  return (
    <div className="py-[4px]">
      <div className="flex items-start gap-2.5">
        <span className="flex-shrink-0 mt-[4px]">
          {isDone
            ? <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <circle cx="5" cy="5" r="4.5" stroke="#4a9966" strokeWidth="1" opacity="0.6" />
              <path d="M3 5L4.5 6.5L7.5 3.5" stroke="#4a9966" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            : isActive
              ? <span className="animate-pulse-dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "#b8906a", display: "block" }} />
              : <span style={{ width: 7, height: 7, borderRadius: "50%", background: "rgba(255,255,255,0.08)", display: "block", border: "1px solid #303038" }} />}
        </span>

        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-medium leading-[1.45]"
            style={{ color: isActive ? "#c0c0c8" : isDone ? "#6b6b7a" : "#52525e" }}>
            {step.detail || step.label}
            {hasMeta && !hasChildren && (
              <button onClick={() => setMetaOpen(o => !o)}
                style={{ marginLeft: 6, color: "#303038", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: "9.5px" }}>
                {metaOpen ? "ẩn ▲" : "xem ▼"}
              </button>
            )}
            {hasChildren && (
              <button onClick={() => setChildrenOpen(o => !o)}
                style={{ marginLeft: 6, color: "#303038", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: "9.5px" }}>
                {childrenOpen ? "ẩn ▲" : `${step.children!.length} bước ▼`}
              </button>
            )}
          </p>

          {hasMeta && !hasChildren && metaOpen && (
            <div className="mt-1 px-2 py-1.5 rounded border border-line" style={{ background: "#0c0c0d" }}>
              {step.meta!.split("\n").filter(Boolean).map((line, i) => (
                <p key={i} className="font-mono text-[9.5px] leading-[1.7]" style={{ color: "#52525e" }}>{line}</p>
              ))}
            </div>
          )}

          {hasChildren && childrenOpen && (
            <div className="mt-1.5 ml-1">
              {step.children!.map((child, i) => (
                <ChildRow key={i} child={child} isLast={i === step.children!.length - 1} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── ThinkingBlock ──────────────────────────────────────────────────────────────
function ThinkingBlock({ steps, phase }: { steps: PipelineStep[]; phase: StreamPhase }) {
  const [isOpen, setIsOpen] = useState(false);
  const prevLenRef = useRef(0);
  const isDone = phase === "streaming" || phase === "done";
  const elapsed = useElapsed(!isDone && steps.length > 0);

  useEffect(() => {
    if (steps.length > 0 && prevLenRef.current === 0) setIsOpen(true);
    prevLenRef.current = steps.length;
  }, [steps.length]);

  useEffect(() => { if (phase === "streaming") setIsOpen(false); }, [phase]);

  if (steps.length === 0) return null;

  const doneCount = steps.filter(s => s.status === "done").length;
  const activeStep = steps.find(s => s.status === "active");
  const headerText = isDone
    ? `Đã phân tích xong`
    : activeStep?.detail
      ? activeStep.detail.replace(/\.\.\.$/, "")
      : "Đang xử lý";
  const timerText = isDone ? `${doneCount} bước` : elapsed > 0 ? `${elapsed}s` : "";

  return (
    <div className="mb-3 rounded-lg overflow-hidden border border-line" style={{ background: "#0e0e10" }}>
      <button
        onClick={() => setIsOpen(o => !o)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2 hover:bg-bg-2 transition-colors duration-150 text-left"
      >
        {isDone
          ? <svg width="11" height="11" viewBox="0 0 11 11" fill="none" className="flex-shrink-0 opacity-40">
            <circle cx="5.5" cy="5.5" r="5" stroke="#4a9966" strokeWidth="1" />
            <path d="M3 5.5L4.8 7.3L8 4" stroke="#4a9966" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          : <span className="w-[5px] h-[5px] rounded-full bg-gold animate-pulse-dot flex-shrink-0" />}

        <span className="flex-1 text-[11.5px] leading-none" style={{ color: isDone ? "#52525e" : "#9090a0" }}>
          {headerText}
        </span>
        {timerText && (
          <span className="font-mono text-[9.5px] flex-shrink-0" style={{ color: isDone ? "#52525e" : "#b8906a" }}>
            {timerText}
          </span>
        )}
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none"
          style={{ flexShrink: 0, color: "#303038", transition: "transform 200ms", transform: isOpen ? "rotate(180deg)" : "rotate(0)" }}>
          <path d="M1.5 3L4.5 6L7.5 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {isOpen && (
        <div className="border-t border-line px-3.5 py-2.5"
          style={{ animation: "fade-up 150ms cubic-bezier(0.16,1,0.3,1) both" }}>
          {steps.map(step => <StepLine key={step.instanceKey} step={step} />)}
        </div>
      )}
    </div>
  );
}

// ── Thinking dots ──────────────────────────────────────────────────────────────
function ThinkingDots() {
  return (
    <div className="flex gap-[5px] items-center py-0.5">
      <span className="w-[4px] h-[4px] rounded-full bg-ink-3 animate-thinking-dot" />
      <span className="w-[4px] h-[4px] rounded-full bg-ink-3 animate-thinking-dot-2" />
      <span className="w-[4px] h-[4px] rounded-full bg-ink-3 animate-thinking-dot-3" />
    </div>
  );
}

// ── Section skeletons ──────────────────────────────────────────────────────────
function SectionSkeletons({ sections }: { sections: AnswerSection[] }) {
  if (!sections || sections.length === 0) return null;

  return (
    <div className="mt-4 pt-4 border-t border-line space-y-4">
      {sections.map((section, i) => {
        // Backend trả về heading/content, frontend dùng title/bullets — normalize cả hai
        const title = (section as any).title ?? (section as any).heading ?? "";
        const bullets = (section as any).bullets ?? (
          // Nếu có content thì tách thành dòng, fallback 3 dòng skeleton
          (section as any).content
            ? (section as any).content.split(/\n|。/).filter(Boolean).slice(0, 4)
            : ["", "", ""]
        );

        return (
          <div key={i} className="animate-fade-up"
            style={{ animationDelay: `${i * 70}ms`, animationFillMode: "both" }}>
            {title && (
              <div className="flex items-center gap-2 mb-2.5">
                <span className="w-px h-3 bg-gold opacity-40 flex-shrink-0 rounded-full" />
                <span className="font-mono text-[10px] tracking-[0.08em] uppercase text-ink-3">
                  {title}
                </span>
              </div>
            )}
            <div className="pl-[14px] space-y-1.5">
              {(Array.isArray(bullets) ? bullets : []).map((_: unknown, j: number) => (
                <div key={j} className="h-[9px] rounded-full bg-line-2 animate-shimmer"
                  style={{ width: `${60 + ((j * 19 + i * 7) % 28)}%` }} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Streaming text ─────────────────────────────────────────────────────────────
function StreamingText({ text, sections }: { text: string; sections: AnswerSection[] }) {
  const stateRef = useRef<{ prevText: string; key: number }>({ prevText: "", key: 0 });
  const { settledText, newChunk, animKey } = useMemo(() => {
    const prev = stateRef.current.prevText;
    const isNew = text.length > prev.length;
    if (isNew) stateRef.current = { prevText: text, key: stateRef.current.key + 1 };
    return { settledText: isNew ? prev : text, newChunk: isNew ? text.slice(prev.length) : "", animKey: stateRef.current.key };
  }, [text]);

  return (
    <div>
      <p className="text-md text-ink-0 leading-[1.72]">
        {settledText}
        {newChunk && <span key={animKey} className="animate-fade-in-text">{newChunk}</span>}
        <span className="inline-block w-[1.5px] h-[14px] bg-gold align-middle ml-[3px] animate-blink"
          style={{ borderRadius: "1px" }} />
      </p>
      {sections && sections.length > 0 && (
        <div className="mt-4 pt-4 border-t border-line">
          <SectionSkeletons sections={sections} />
        </div>
      )}
    </div>
  );
}

// ── Public ─────────────────────────────────────────────────────────────────────
export interface StreamingMessageProps {
  phase: StreamPhase;
  steps: PipelineStep[];
  text: string;
  sections: AnswerSection[];
}

export default function StreamingMessage({ phase, steps, text, sections }: StreamingMessageProps) {
  const hasSteps = steps.length > 0;
  const showThinking = phase === "thinking" && text === "" && !hasSteps;
  const safeSections = sections ?? [];

  return (
    <div className="mb-14 animate-fade-up">
      <AgentLabel pulsing />
      {hasSteps && <ThinkingBlock steps={steps} phase={phase} />}
      {showThinking && <ThinkingDots />}
      {phase === "streaming" && <StreamingText text={text} sections={safeSections} />}
      {phase === "thinking" && safeSections.length > 0 && <SectionSkeletons sections={safeSections} />}
    </div>
  );
}