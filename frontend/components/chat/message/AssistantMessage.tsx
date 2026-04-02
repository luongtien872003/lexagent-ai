import AgentLabel              from "./AgentLabel";
import StructuredAnswerComp    from "./StructuredAnswer";
import ContentRenderer         from "./ContentRenderer";
import CitationChip            from "./CitationChip";
import type {
  AssistantMessage as AssistantMessageType,
  CitationHoverState,
} from "@/lib/types";

interface AssistantMessageProps {
  message:      AssistantMessageType;
  activeCiteId: string | null;
  hoverState:   CitationHoverState;
  onCiteClick:  (id: string) => void;
  onCiteEnter:  (id: string, rect: DOMRect) => void;
  onCiteLeave:  () => void;
}

/**
 * AssistantMessage is a routing shell.
 *
 * structured data present → StructuredAnswerComp (rich path)
 * no structured data       → ContentRenderer + chip row (fallback path)
 *
 * All hover/citation props thread through both paths so citation state
 * is always in sync: inline buttons, chips, panel, and tooltip all
 * reflect the same activeCiteId and hoverState.
 *
 * The outer div uses animate-fade-up for the message appear animation.
 * AgentLabel is rendered once at the top — never duplicated.
 */
export default function AssistantMessage({
  message,
  activeCiteId,
  hoverState,
  onCiteClick,
  onCiteEnter,
  onCiteLeave,
}: AssistantMessageProps) {
  const hasStructured = !!(
    message.structured &&
    (message.structured.summary.length > 0 || message.structured.sections.length > 0)
  );

  return (
    <div className="mb-14 animate-fade-up">
      <AgentLabel />

      {hasStructured ? (
        <StructuredAnswerComp
          structured={message.structured!}
          citations={message.citations}
          activeCiteId={activeCiteId}
          hoverState={hoverState}
          onCiteClick={onCiteClick}
          onCiteEnter={onCiteEnter}
          onCiteLeave={onCiteLeave}
        />
      ) : (
        <>
          <div className="text-md text-ink-0 leading-[1.72]">
            <ContentRenderer
              blocks={message.content}
              activeCiteId={activeCiteId}
              hoverState={hoverState}
              onCiteClick={onCiteClick}
              onCiteEnter={onCiteEnter}
              onCiteLeave={onCiteLeave}
            />
          </div>

          {message.citations.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-5">
              {message.citations.map(cit => (
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
        </>
      )}
    </div>
  );
}
