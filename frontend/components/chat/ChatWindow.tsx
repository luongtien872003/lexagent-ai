"use client";

import { useRef } from "react";
import ChatTopbar       from "./ChatTopbar";
import EmptyState       from "./EmptyState";
import ChatInput        from "./ChatInput";
import UserMessage      from "./message/UserMessage";
import AssistantMessage from "./message/AssistantMessage";
import StreamingMessage from "./message/StreamingMessage";
import CitationTooltip  from "./message/CitationTooltip";
import { useScrollToBottom } from "@/lib/hooks/useScrollToBottom";
import type {
  Message,
  PipelineStep,
  StreamPhase,
  AnswerSection,
  CitationHoverState,
  Citation,
} from "@/lib/types";

interface ChatWindowProps {
  title:             string;
  modelTier:         import("@/lib/types").ModelTierId;
  onModelTierChange: (tier: import("@/lib/types").ModelTierId) => void;
  messages:          Message[];
  isStreaming:    boolean;
  streamPhase:    StreamPhase;
  streamSteps:    PipelineStep[];
  streamText:     string;
  streamSections: AnswerSection[];
  activeCiteId:   string | null;
  hoverState:     CitationHoverState;
  streamError:    string | null;       // NEW: surface backend errors to the user
  onCiteClick:    (id: string) => void;
  onCiteEnter:    (id: string, rect: DOMRect) => void;
  onCiteLeave:    () => void;
  cancelLeave:    () => void;          // NEW: tooltip's onMouseEnter calls this
  onSubmit:       (text: string) => void;
}

export default function ChatWindow({
  title, modelTier, onModelTierChange, messages, isStreaming,
  streamPhase, streamSteps, streamText, streamSections,
  activeCiteId, hoverState, streamError,
  onCiteClick, onCiteEnter, onCiteLeave, cancelLeave, onSubmit,
}: ChatWindowProps) {
  const inputRef    = useRef<HTMLTextAreaElement>(null);
  const sentinelRef = useScrollToBottom(messages, streamText, streamPhase);

  function fillInput(text: string) {
    const ta = inputRef.current;
    if (!ta) return;
    ta.value = text;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
    ta.focus();
  }

  const isEmpty = messages.length === 0 && !isStreaming;

  // Resolve hovered citation for tooltip
  let hoverCitation: Citation | null = null;
  for (const msg of messages) {
    if (msg.role === "assistant") {
      const found = msg.citations.find(c => c.id === hoverState.id);
      if (found) { hoverCitation = found; break; }
    }
  }
  // hoverRecord is now sourced from citation.chuong_label — no DIEU_DB lookup needed
  const hoverRecord = null;

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-bg-base">
      <ChatTopbar title={title} modelTier={modelTier} onModelTierChange={onModelTierChange} />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {isEmpty ? (
          <EmptyState onSelectSuggestion={fillInput} />
        ) : (
          <div className="max-w-[680px] mx-auto px-8 pt-10 pb-4">
            {messages.map((msg) =>
              msg.role === "user" ? (
                <UserMessage key={msg.id} text={msg.text} />
              ) : (
                <AssistantMessage
                  key={msg.id}
                  message={msg}
                  activeCiteId={activeCiteId}
                  hoverState={hoverState}
                  onCiteClick={onCiteClick}
                  onCiteEnter={onCiteEnter}
                  onCiteLeave={onCiteLeave}
                />
              )
            )}

            {isStreaming && (
              <StreamingMessage
                phase={streamPhase}
                steps={streamSteps}
                text={streamText}
                sections={streamSections}
              />
            )}

            {/* Error state — visible, actionable, not console.error */}
            {streamError && !isStreaming && (
              <div className="mb-8 animate-fade-up">
                <div className="flex items-start gap-3 px-4 py-3 rounded-lg
                                border border-[rgba(201,90,90,0.2)]
                                bg-[rgba(201,90,90,0.04)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#c95a5a] flex-shrink-0 mt-[5px]" />
                  <div>
                    <p className="text-sm text-ink-1 leading-snug">
                      Không nhận được phản hồi từ hệ thống.
                    </p>
                    <p className="text-xs text-ink-3 mt-1">
                      Vui lòng thử lại hoặc kiểm tra kết nối.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div ref={sentinelRef} />
          </div>
        )}
      </div>

      <ChatInput ref={inputRef} onSubmit={onSubmit} disabled={isStreaming} />

      {/* Citation tooltip — cancelLeave is now properly wired */}
      <CitationTooltip
        citation={hoverCitation}
        anchorRect={hoverState.anchorRect}
        record={hoverRecord}
        onTooltipEnter={cancelLeave}
        onTooltipLeave={onCiteLeave}
        onCiteClick={onCiteClick}
      />
    </div>
  );
}
