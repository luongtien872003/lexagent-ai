"use client";

import { useState, useCallback, useRef, useMemo } from "react";
import { SEED_CONVERSATIONS } from "@/lib/data";
// FIX: `getSimulatedResponse` was imported but never called after real streaming
// was implemented. Dead imports signal sloppy cleanup after demos. Removed.
import { useCitationHover } from "./useCitationHover";
import type {
  Conversation, Message, AssistantMessage,
  ContentBlock, Citation, CitationColor,
  CitationHoverState, StructuredAnswer, AnswerSection,
  PipelineStep, StreamPhase, StreamState, ModelTierId,
} from "@/lib/types";

// ── Constants ─────────────────────────────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
  classifying: "Hiểu câu hỏi",
  retrieving:  "Đang tìm",
  reranking:   "Kiểm tra",
  generating:  "Soạn trả lời",
};
const CITE_COLORS: CitationColor[] = ["amber", "green", "blue", "purple"];

// ── Helpers ───────────────────────────────────────────────────────────────

function appendOrUpdateStep(
  steps: PipelineStep[],
  stepId: string,
  detail: string,
  meta: string,
  newStep: boolean,
): PipelineStep[] {
  const label = STEP_LABELS[stepId] ?? stepId;
  const lastActive = steps.reduce<number>((acc, s, i) => s.status === "active" ? i : acc, -1);

  if (!newStep && lastActive >= 0) {
    // Append a child node to the current active step (tree branch)
    return steps.map((s, i) => {
      if (i !== lastActive) return s;
      const prevChildren = s.children ?? [];
      // Mark previous child as done, add new child as active
      const closedChildren = prevChildren.map(c => ({ ...c, done: true }));
      const newChild: import("@/lib/types").StepChild = { label: detail, meta, done: false };
      return {
        ...s,
        detail,
        meta: meta || s.meta,
        children: [...closedChildren, newChild],
      };
    });
  }

  // new_step=true: close current active step + append new top-level step
  const instanceKey = `${stepId}_${steps.filter(s => s.id === stepId).length}`;
  const closed = steps.map(s =>
    s.status === "active"
      ? { ...s, status: "done" as const, children: (s.children ?? []).map(c => ({ ...c, done: true })) }
      : s
  );
  return [
    ...closed,
    { id: stepId, instanceKey, label, status: "active" as const, detail, meta, children: [] },
  ];
}

function completeAllSteps(steps: PipelineStep[]): PipelineStep[] {
  return steps.map(s => ({
    ...s,
    status: "done" as const,
    children: (s.children ?? []).map(c => ({ ...c, done: true })),
  }));
}

// API base URL — set NEXT_PUBLIC_API_URL in .env.local to override
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function mapBackendCitation(
  c: {
    so_dieu: number; ten_dieu: string;
    index?: number; noi_dung_snippet?: string;
    chuong_so?: number; ten_chuong?: string;
    so_khoan?: number;
  },
  arrayIndex: number,
): Citation {
  const chuong_label = c.chuong_so
    ? `Chương ${c.chuong_so}${c.ten_chuong ? " — " + c.ten_chuong : ""}`
    : undefined;
  return {
    id:           `d${c.so_dieu}`,
    label:        `Điều ${c.so_dieu} — ${c.ten_dieu}`,
    num:          String(c.index ?? arrayIndex + 1),
    color:        CITE_COLORS[arrayIndex % CITE_COLORS.length],
    snippet:      c.noi_dung_snippet,
    chuong_label,
    so_khoan:     c.so_khoan && c.so_khoan > 0 ? c.so_khoan : undefined,
  };
}

// ── Public interface ───────────────────────────────────────────────────────

export interface UseChatReturn {
  conversations:      Conversation[];
  activeId:           string;
  activeConv:         Conversation | undefined;
  isStreaming:        boolean;
  streamState:        StreamState;
  streamError:        string | null;      // NEW
  activeCiteId:       string | null;
  hoverState:         CitationHoverState;
  modelTier:          ModelTierId;
  setModelTier:       (tier: ModelTierId) => void;
  selectConv:         (id: string) => void;
  newChat:            () => void;
  submitMessage:      (text: string) => Promise<void>;
  toggleCitation:     (id: string) => void;
  navigateToCitation: (id: string) => void;
  closeCitation:      () => void;
  onCiteEnter:        (id: string, rect: DOMRect) => void;
  onCiteLeave:        () => void;
  cancelLeave:        () => void;         // NEW: for tooltip's onMouseEnter
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useChat(): UseChatReturn {
  const [conversations, setConversations] = useState<Conversation[]>(SEED_CONVERSATIONS);
  const [activeId,      setActiveId]      = useState<string>(SEED_CONVERSATIONS[0].id);
  const [modelTier,     setModelTier]      = useState<ModelTierId>("fast");
  const [isStreaming,   setIsStreaming]    = useState(false);
  const [streamError,   setStreamError]   = useState<string | null>(null);
  const [streamState,   setStreamState]   = useState<StreamState>({
    phase:    "thinking",
    steps:    [],
    text:     "",
    sections: [],
  });
  const [activeCiteId, setActiveCiteId] = useState<string | null>(null);

  const { hoverState, onCiteEnter, onCiteLeave, cancelLeave } = useCitationHover();

  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;

  const activeConv = useMemo(
    () => conversations.find(c => c.id === activeId),
    [conversations, activeId],
  );

  // ── Conversation management ───────────────────────────────────────────

  const selectConv = useCallback((id: string) => {
    if (isStreaming) return;
    setActiveId(id);
    setActiveCiteId(null);
    setStreamError(null);
  }, [isStreaming]);

  const newChat = useCallback(() => {
    if (isStreaming) return;
    const id = `conv-${Date.now()}`;
    setConversations(prev => [
      { id, title: "Phiên tư vấn mới", createdAt: new Date().toISOString(), messages: [] },
      ...prev,
    ]);
    setActiveId(id);
    setActiveCiteId(null);
    setStreamError(null);
  }, [isStreaming]);

  // ── Citation panel ────────────────────────────────────────────────────

  const toggleCitation = useCallback((id: string) => {
    setActiveCiteId(prev => prev === id ? null : id);
  }, []);

  const navigateToCitation = useCallback((id: string) => {
    setActiveCiteId(id);
  }, []);

  const closeCitation = useCallback(() => {
    setActiveCiteId(null);
  }, []);

  // ── Message submission ────────────────────────────────────────────────

  const submitMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;

    const convId = activeIdRef.current;

    const userMsg: Message = {
      role: "user",
      id:   `u-${Date.now()}`,
      text: trimmed,
    };

    setStreamError(null);
    setConversations(prev =>
      prev.map(c => c.id !== convId ? c : {
        ...c,
        title:    c.messages.length === 0 ? trimmed.slice(0, 48) : c.title,
        messages: [...c.messages, userMsg],
      })
    );

    setIsStreaming(true);
    setStreamState({ phase: "thinking", steps: [], text: "", sections: [] });

    try {
      const response = await fetch(
        `${API_URL}/api/conversations/${convId}/messages`,
        {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ content: trimmed, stream: true, mode: "agentic", model_tier: modelTier }),
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) {
        throw new Error("No response body");
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer              = "";
      let pendingEvtType      = "";
      let accumulated         = "";
      let switchedToStreaming  = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";

        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (line === "")                { pendingEvtType = ""; continue; }
          if (line.startsWith("event: ")) { pendingEvtType = line.slice(7).trim(); continue; }
          if (!line.startsWith("data: ")) continue;

          const rawData = line.slice(6).trim();
          if (!rawData || rawData === "[DONE]") continue;

          let event: Record<string, unknown>;
          try { event = JSON.parse(rawData); }
          catch { continue; }

          const evtType = (event.type as string | undefined) || pendingEvtType;

          if (evtType === "status") {
            const step    = (event.step     as string)  ?? "";
            const detail  = (event.detail   as string)  ?? "";
            const meta    = (event.meta     as string)  ?? "";
            const newStep = (event.new_step as boolean) ?? true;
            setStreamState(s => ({
              ...s,
              steps: appendOrUpdateStep(s.steps, step, detail, meta, newStep),
            }));
          }
          else if (evtType === "sections") {
            const sections = (event.sections as AnswerSection[]) ?? [];
            setStreamState(s => ({ ...s, sections }));
          }
          else if (evtType === "token") {
            const content = (event.content as string) ?? "";
            accumulated += content;
            setStreamState(s => {
              if (!switchedToStreaming) {
                switchedToStreaming = true;
                return { ...s, phase: "streaming", steps: completeAllSteps(s.steps), text: content };
              }
              return { ...s, text: s.text + content };
            });
          }
          else if (evtType === "done") {
            const msgData = event.message as {
              id?:         string;
              content?:    string;
              citations?:  Array<{
                so_dieu: number; ten_dieu: string;
                index?: number; noi_dung_snippet?: string;
              }>;
              structured?: StructuredAnswer | null;
            };

            const rawCitations = msgData.citations ?? [];
            const mapped       = rawCitations.map((c, i) => mapBackendCitation(c, i));
            const seen         = new Set<string>();
            const unique       = mapped.filter(c => !seen.has(c.id) && seen.add(c.id));

            const structured   = msgData.structured ?? null;
            const summaryText  = structured?.summary ?? accumulated ?? "";
            const content: ContentBlock[] = [{ type: "text", text: summaryText }];

            const assistantMsg: AssistantMessage = {
              role:       "assistant",
              id:         msgData.id ?? `a-${Date.now()}`,
              content,
              citations:  unique,
              structured,
            };

            setConversations(prev =>
              prev.map(c => c.id !== convId
                ? c
                : { ...c, messages: [...c.messages, assistantMsg] }
              )
            );
          }
          else if (evtType === "error") {
            console.error("[Pipeline]", event.detail);
            setStreamError("Pipeline error");
          }
        }
      }
    } catch (err) {
      // Show error to user — not silent console.error
      setStreamError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStreaming(false);
      setStreamState(prev => ({
        phase:    "done",
        steps:    completeAllSteps(prev.steps),
        text:     "",
        sections: [],
      }));
    }
  }, [isStreaming]);

  return {
    conversations, activeId, activeConv,
    modelTier, setModelTier,
    isStreaming, streamState, streamError,
    activeCiteId, hoverState,
    selectConv, newChat, submitMessage,
    toggleCitation, navigateToCitation, closeCitation,
    onCiteEnter, onCiteLeave, cancelLeave,
  };
}
