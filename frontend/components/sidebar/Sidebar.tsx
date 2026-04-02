import { IconPlus } from "@/components/ui/icons";
import { formatRelativeDate, isToday } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

interface ConversationGroup { label: string; items: Conversation[] }

function groupByDate(convs: Conversation[]): ConversationGroup[] {
  const today:  Conversation[] = [];
  const older: Conversation[] = [];
  for (const c of convs) {
    (isToday(c.createdAt) ? today : older).push(c);
  }
  const groups: ConversationGroup[] = [];
  if (today.length) groups.push({ label: "Hôm nay",  items: today });
  if (older.length) groups.push({ label: "Trước đó", items: older });
  return groups;
}

interface SidebarProps {
  conversations: Conversation[];
  activeId:      string;
  onSelect:      (id: string) => void;
  onNewChat:     () => void;
}

export default function Sidebar({ conversations, activeId, onSelect, onNewChat }: SidebarProps) {
  return (
    <aside className="w-sidebar flex-shrink-0 flex flex-col bg-bg-1 border-r border-line">

      <div className="h-[52px] flex items-center px-4 flex-shrink-0 border-b border-line">
        <span className="font-serif text-lg text-ink-0 tracking-[-0.01em] leading-none select-none">
          Lex<em className="text-gold not-italic">Agent</em>
        </span>
      </div>

      <div className="px-3 pt-3 pb-1 flex-shrink-0">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-md
                     text-ink-2 text-sm
                     transition-colors duration-100
                     hover:bg-bg-2 hover:text-ink-1"
        >
          <IconPlus className="w-3 h-3 flex-shrink-0 opacity-75" />
          Phiên mới
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-3 scrollbar-none">
        {groupByDate(conversations).map((group) => (
          <div key={group.label} className="mt-4">
            <p className="px-1 mb-1 text-2xs uppercase tracking-[0.08em] text-ink-3 select-none">
              {group.label}
            </p>
            {group.items.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                title={formatRelativeDate(conv.createdAt)}
                suppressHydrationWarning
                className={[
                  "w-full flex items-center px-3 py-[7px] rounded-md mb-px",
                  "text-left text-sm truncate transition-colors duration-100",
                  conv.id === activeId
                    ? "bg-bg-3 text-ink-0"
                    : "text-ink-1 hover:bg-bg-2 hover:text-ink-0",
                ].join(" ")}
              >
                {conv.title}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="px-3 py-3 border-t border-line flex-shrink-0">
        <button className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md
                           transition-colors duration-100 hover:bg-bg-2">
          <div className="w-[26px] h-[26px] rounded-full flex-shrink-0
                          bg-gold-dim border border-gold-border
                          flex items-center justify-center
                          font-mono text-tag tracking-wider text-gold">
            NT
          </div>
          <div className="text-left min-w-0">
            <p className="text-sm text-ink-0 leading-tight truncate">Nguyễn Thanh</p>
            <p className="text-xs text-ink-2 leading-tight mt-[2px]">Luật sư lao động</p>
          </div>
        </button>
      </div>

    </aside>
  );
}
