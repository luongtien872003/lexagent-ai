// DEMO TELL REMOVED: The previous EmptyState showed each suggestion card with
// TWO lines: a label ("Sa thải đơn phương") and the full query text
// ("Người sử dụng lao động có thể đơn phương sa thải khi nào?").
//
// Showing the exact query text is the "I'm a demo" tell. It signals:
// "We don't trust you to know what to type, here is literally the text."
// Real products show compact labels. The user clicks the label and it submits.
// They don't need to read the full query first.
//
// Also removed: the "Gợi ý" section label. If it's on the empty state screen,
// users know it's a suggestion without needing to be told.

const SUGGESTIONS = [
  { label: "Sa thải đơn phương",   query: "Người sử dụng lao động có thể đơn phương sa thải khi nào?"       },
  { label: "Thời gian thử việc",   query: "Thời gian thử việc tối đa theo BLLĐ 2012 là bao lâu?"            },
  { label: "Bảo vệ thai sản",      query: "Quyền lợi lao động nữ khi mang thai theo luật?"                   },
  { label: "Làm thêm giờ",         query: "Giới hạn làm thêm giờ hàng tháng và hàng năm là bao nhiêu?"       },
  { label: "Loại hợp đồng",        query: "Các loại hợp đồng lao động theo BLLĐ 2012?"                       },
  { label: "Trợ cấp thôi việc",    query: "Điều kiện và mức trợ cấp thôi việc theo luật lao động?"           },
] as const;

interface EmptyStateProps {
  onSelectSuggestion: (text: string) => void;
}

export default function EmptyState({ onSelectSuggestion }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full pb-16 px-8">

      {/* Brand lockup — serif, understated */}
      <div className="mb-10 text-center">
        <h1 className="font-serif text-3xl text-ink-0 tracking-[-0.02em] leading-none mb-3">
          Lex<em className="text-gold not-italic">Agent</em>
        </h1>
        <p className="text-sm text-ink-2">
          Bộ luật Lao động 10/2012/QH13
        </p>
      </div>

      {/* Compact suggestion grid — label only, no query preview */}
      <div className="w-full max-w-[500px]">
        <div className="grid grid-cols-2 gap-[5px]">
          {SUGGESTIONS.map(({ label, query }) => (
            <button
              key={label}
              onClick={() => onSelectSuggestion(query)}
              className="text-left px-4 py-2.5 rounded-md
                         border border-line
                         transition-all duration-150
                         hover:border-line-2 hover:bg-bg-1"
            >
              <p className="text-sm text-ink-2 transition-colors duration-100 hover:text-ink-1">
                {label}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
