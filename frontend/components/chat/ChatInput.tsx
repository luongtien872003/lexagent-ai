"use client";

import { forwardRef, useState } from "react";
import { IconSend } from "@/components/ui/icons";

interface ChatInputProps {
  onSubmit:  (text: string) => void;
  disabled?: boolean;
}

const ChatInput = forwardRef<HTMLTextAreaElement, ChatInputProps>(
  function ChatInput({ onSubmit, disabled = false }, ref) {
    const [focused, setFocused] = useState(false);

    function getTextarea() {
      if (!ref || typeof ref === "function") return null;
      return ref.current;
    }

    function submit() {
      const ta  = getTextarea();
      const val = ta?.value.trim();
      if (!val || disabled) return;
      onSubmit(val);
      if (ta) { ta.value = ""; ta.style.height = "auto"; }
    }

    function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    }

    function autoResize(el: HTMLTextAreaElement) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }

    return (
      <div className="px-8 pb-6 pt-3 flex-shrink-0">
        <div className="max-w-[680px] mx-auto">

          <div className="relative rounded-xl border border-line bg-bg-1
                          focus-within:border-line-2 focus-within:bg-bg-2
                          transition-all duration-150">
            <textarea
              ref={ref}
              rows={1}
              disabled={disabled}
              placeholder="Đặt câu hỏi về pháp luật lao động…"
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={handleKeyDown}
              onChange={(e) => autoResize(e.target)}
              className="w-full bg-transparent outline-none
                         pl-4 pr-12 pt-[13px] pb-[13px]
                         text-base text-ink-0 leading-[1.55]
                         placeholder:text-ink-2
                         min-h-[48px] max-h-[160px] overflow-y-auto
                         disabled:cursor-not-allowed"
            />

            <button
              onClick={submit}
              disabled={disabled}
              className="absolute right-2 bottom-2
                         w-8 h-8 rounded-lg
                         flex items-center justify-center
                         bg-gold text-bg-base
                         transition-all duration-100
                         hover:brightness-110 active:scale-95
                         disabled:bg-bg-3 disabled:text-ink-2
                         disabled:cursor-not-allowed disabled:scale-100 disabled:brightness-100"
            >
              <IconSend className="w-[13px] h-[13px]" />
            </button>
          </div>

          {/* Hint only when focused — not permanent noise */}
          <p className={[
            "text-center mt-2 text-mono-label text-ink-3 select-none",
            "transition-opacity duration-150",
            focused ? "opacity-100" : "opacity-0",
          ].join(" ")}>
            Enter để gửi · Shift+Enter xuống dòng
          </p>

        </div>
      </div>
    );
  }
);

export default ChatInput;
