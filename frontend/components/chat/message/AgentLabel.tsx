// DEMO TELL REMOVED: The previous AgentLabel showed "● LEXAGENT" above EVERY
// assistant message. In a conversation with 6 turns, "LEXAGENT" appears 6 times.
// By turn 3 the user knows who is answering. Repeating the agent name above every
// single response is what a hackathon demo does to show "look, it has branding."
//
// Real products (Harvey, Notion AI, Cursor) use a subtle left-rail indicator —
// a small dot or avatar — that appears ONCE per response turn, not as a noisy
// header. This component now renders a 6px gold dot on the left margin.
// The dot is slightly offset to create the implied left rail that professional
// AI products use to separate agent turns from user turns.

interface AgentLabelProps {
  pulsing?: boolean;
}

export default function AgentLabel({ pulsing = false }: AgentLabelProps) {
  return (
    <div className="flex items-center mb-3">
      <span
        className={[
          "w-[6px] h-[6px] rounded-full flex-shrink-0",
          "bg-gold opacity-60",
          pulsing ? "animate-pulse-dot" : "",
        ].join(" ")}
      />
    </div>
  );
}
