"use client";

import { useCallback } from "react";
import Sidebar     from "@/components/sidebar/Sidebar";
import ChatWindow  from "@/components/chat/ChatWindow";
import SourcePanel from "@/components/source-panel/SourcePanel";
import { useChat } from "@/lib/hooks/useChat";

/**
 * FIX: Removed DIEU_DB import and activeArticle computation.
 * SourcePanel now fetches article data internally from the backend on demand.
 * This fixes the citation click bug where any article outside the 4-item
 * DIEU_DB (d36, d38, d39, d155) would silently render nothing.
 */

export default function Page() {
  const {
    conversations,
    activeId,
    activeConv,
    isStreaming,
    streamState,
    streamError,
    modelTier,
    setModelTier,
    activeCiteId,
    hoverState,
    selectConv,
    newChat,
    submitMessage,
    toggleCitation,
    navigateToCitation,
    closeCitation,
    onCiteEnter,
    onCiteLeave,
    cancelLeave,
  } = useChat();

  // Resolve the full Citation object (with snippet + chuong_label) for the active citation
  // so SourcePanel and CitationTooltip can use snippet-based matching without DIEU_DB
  const activeCitation = activeCiteId
    ? (() => {
        for (const conv of conversations) {
          for (const msg of conv.messages) {
            if (msg.role === "assistant") {
              const found = msg.citations.find(c => c.id === activeCiteId);
              if (found) return found;
            }
          }
        }
        return null;
      })()
    : null;

  const handleClose = useCallback(() => closeCitation(), [closeCitation]);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConv}
        onNewChat={newChat}
      />

      <div className="flex flex-1 min-w-0 overflow-hidden">
        <ChatWindow
          title={activeConv?.title ?? "Phiên tư vấn mới"}
          modelTier={modelTier}
          onModelTierChange={setModelTier}
          messages={activeConv?.messages ?? []}
          isStreaming={isStreaming}
          streamPhase={streamState.phase}
          streamSteps={streamState.steps}
          streamText={streamState.text}
          streamSections={streamState.sections}
          activeCiteId={activeCiteId}
          hoverState={hoverState}
          streamError={streamError}
          onCiteClick={toggleCitation}
          onCiteEnter={onCiteEnter}
          onCiteLeave={onCiteLeave}
          cancelLeave={cancelLeave}
          onSubmit={submitMessage}
        />

        {/* SourcePanel fetches article data itself — no DIEU_DB lookup here */}
        <SourcePanel
          activeCitation={activeCitation}
          onNavigate={navigateToCitation}
          onClose={handleClose}
        />
      </div>
    </div>
  );
}
