"use client";

import { useState, useRef, useEffect } from "react";
import { MODEL_TIERS } from "@/lib/types";
import type { ModelTierId } from "@/lib/types";

interface ChatTopbarProps {
  title:             string;
  modelTier:         ModelTierId;
  onModelTierChange: (tier: ModelTierId) => void;
}

export default function ChatTopbar({ title, modelTier, onModelTierChange }: ChatTopbarProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const activeTier = MODEL_TIERS.find(t => t.id === modelTier) ?? MODEL_TIERS[0];

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="flex items-center justify-between h-[52px] px-6 border-b border-line flex-shrink-0">

      {/* Title */}
      <span className="text-base font-medium text-ink-0 tracking-[-0.01em] truncate mr-4">
        {title}
      </span>

      <div className="flex items-center gap-3 flex-shrink-0">

        {/* Corpus badge */}
        <div className="flex items-center gap-1.5">
          <span className="w-[5px] h-[5px] rounded-full bg-ok flex-shrink-0" />
          <span className="font-mono text-[10.5px] tracking-[0.04em] uppercase text-ink-2">
            BLLĐ 2012
          </span>
        </div>

        {/* Divider */}
        <span className="w-px h-3 bg-line-2" />

        {/* Model picker */}
        <div ref={ref} className="relative">
          <button
            onClick={() => setOpen(o => !o)}
            className={[
              "flex items-center gap-2 px-2.5 py-1.5 rounded-md border transition-all duration-150",
              open
                ? "border-line-2 bg-bg-2"
                : "border-transparent hover:border-line hover:bg-bg-2",
            ].join(" ")}
          >
            {/* Tier color dot */}
            <TierDot tier={activeTier.id} />
            <span className="text-[11.5px] font-medium text-ink-1">
              {activeTier.name}
            </span>
            {/* Cost badge */}
            <span className="font-mono text-[9.5px] text-ink-3 bg-bg-3 border border-line px-1.5 py-[2px] rounded-xs">
              ~{activeTier.cost_vnd}đ
            </span>
            {/* Chevron */}
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none"
              style={{ transition: "transform 150ms", transform: open ? "rotate(180deg)" : "rotate(0)" }}
              className="text-ink-3 flex-shrink-0">
              <path d="M1.5 3L4.5 6L7.5 3" stroke="currentColor" strokeWidth="1.4"
                    strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>

          {/* Dropdown */}
          {open && (
            <div
              className="absolute right-0 top-full mt-1.5 w-64 rounded-lg border border-line bg-bg-2 shadow-none overflow-hidden z-50"
              style={{ animation: "fade-up 140ms cubic-bezier(0.16,1,0.3,1) both" }}
            >
              <div className="px-3 pt-2.5 pb-1">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.07em] text-ink-3 select-none">
                  Chọn model
                </p>
              </div>

              {MODEL_TIERS.map((tier) => {
                const isActive = tier.id === modelTier;
                return (
                  <button
                    key={tier.id}
                    onClick={() => { onModelTierChange(tier.id); setOpen(false); }}
                    className={[
                      "w-full flex items-start gap-3 px-3 py-2.5 transition-colors duration-100 text-left",
                      isActive ? "bg-bg-3" : "hover:bg-bg-3",
                    ].join(" ")}
                  >
                    <TierDot tier={tier.id} size={6} className="mt-[3px]" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={[
                          "text-[12px] font-medium leading-none",
                          isActive ? "text-ink-0" : "text-ink-1",
                        ].join(" ")}>
                          {tier.name}
                        </span>
                        {isActive && (
                          <span className="w-[5px] h-[5px] rounded-full bg-gold flex-shrink-0" />
                        )}
                      </div>
                      <p className="text-[11px] text-ink-3 mt-[3px] leading-snug">
                        {tier.description}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="font-mono text-[11px] text-ink-2">~{tier.cost_vnd}đ</p>
                      <p className="font-mono text-[9px] text-ink-3 mt-[1px]">/câu hỏi</p>
                    </div>
                  </button>
                );
              })}

              <div className="px-3 py-2 border-t border-line mt-1">
                <p className="text-[10px] text-ink-3 leading-snug">
                  Chi phí ước tính. Decomposer + Verifier luôn dùng model nhanh nhất để tiết kiệm.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TierDot({
  tier, size = 5, className = "",
}: { tier: ModelTierId; size?: number; className?: string }) {
  const colors: Record<ModelTierId, string> = {
    fast:     "#52525e",
    balanced: "#b8906a",
    precise:  "#4a9966",
  };
  return (
    <span
      className={`rounded-full flex-shrink-0 ${className}`}
      style={{ width: size, height: size, background: colors[tier] }}
    />
  );
}
