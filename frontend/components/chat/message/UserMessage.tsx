// DEMO TELL REMOVED: The previous UserMessage used `bg-bg-2 border border-line-2
// rounded-2xl rounded-br-sm` — a chat bubble with an iMessage-style asymmetric corner.
// This is the visual language of WhatsApp and iMessage. Not Harvey. Not legal software.
//
// Harvey shows user messages as plain right-aligned text with NO bubble, no background,
// no border. Just the text itself, slightly muted, right-aligned. The asymmetry of
// left (agent) vs right (user) is enough to distinguish turns. Adding a bubble signals
// "I built this by copying a chat app tutorial."

interface UserMessageProps { text: string }

export default function UserMessage({ text }: UserMessageProps) {
  return (
    <div className="flex justify-end mb-10 animate-fade-up">
      <p className="max-w-[68%] text-md text-ink-1 leading-[1.65] whitespace-pre-wrap text-right">
        {text}
      </p>
    </div>
  );
}
