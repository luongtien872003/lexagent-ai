"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { formatArticleId } from "@/lib/utils";
import { IconX } from "@/components/ui/icons";
import type { DieuRecord, Citation } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DiemData { ky_hieu: string; noi_dung: string }
interface KhoanData { so_khoan: number; noi_dung: string; diem?: DiemData[] }
interface ArticleFetched {
  so_dieu: number; ten_dieu: string; chuong_so: number; ten_chuong: string;
  khoan: KhoanData[]; references: { target_dieu: number }[];
}

function mapFetchedToRecord(data: ArticleFetched): DieuRecord {
  return {
    id:      `d${data.so_dieu}`,
    num:     `Điều ${data.so_dieu}`,
    title:   data.ten_dieu,
    chuong:  `Chương ${data.chuong_so} — ${data.ten_chuong}`,
    khoans:  data.khoan.map((k, i) => ({
      num:  `Khoản ${k.so_khoan ?? i + 1}`,
      text: k.noi_dung,
      diem: k.diem ?? [],
    })),
    related: [...new Set(
      (data.references ?? []).map(r => `d${r.target_dieu}`)
    )].filter(id => id !== `d${data.so_dieu}`),
  };
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface SourcePanelProps {
  activeCitation: Citation | null;
  onNavigate:     (id: string) => void;
  onClose:        () => void;
}

export default function SourcePanel({ activeCitation, onNavigate, onClose }: SourcePanelProps) {
  const [article, setArticle] = useState<DieuRecord | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeCitation) { setArticle(null); return; }
    const soDieu = activeCitation.id.replace(/^d/, "");
    let cancelled = false;
    setLoading(true);

    fetch(`${API_URL}/api/documents/10.2012.QH13/dieu/${soDieu}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then((data: ArticleFetched) => { if (!cancelled) setArticle(mapFetchedToRecord(data)); })
      .catch(() => { if (!cancelled) setArticle(null); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [activeCitation?.id]);

  const isOpen = activeCitation !== null;

  return (
    <aside className={[
      "flex-shrink-0 flex flex-col overflow-hidden",
      "bg-bg-1 border-l border-line",
      "transition-[width] duration-300 ease-spring",
      isOpen ? "w-source" : "w-0",
    ].join(" ")}>
      {isOpen && (
        loading ? <PanelSkeleton onClose={onClose} />
        : article ? (
          <PanelContent
            article={article}
            activeCitation={activeCitation}
            onNavigate={onNavigate}
            onClose={onClose}
          />
        ) : <PanelEmpty onClose={onClose} />
      )}
    </aside>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────
function PanelSkeleton({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col h-full">
      <PanelHeader onClose={onClose} />
      <div className="px-5 pt-5 pb-4 border-b border-line flex-shrink-0 space-y-3">
        <div className="h-6 w-20 rounded-full bg-line animate-shimmer" />
        <div className="h-3.5 w-3/4 rounded-full bg-line animate-shimmer" />
        <div className="flex gap-1.5 mt-3">
          <div className="h-4 w-28 rounded-sm bg-line animate-shimmer" />
          <div className="h-4 w-16 rounded-sm bg-line animate-shimmer" />
        </div>
      </div>
      <div className="flex-1 px-5 pt-4 space-y-5">
        {[80, 65, 90].map((w, i) => (
          <div key={i} className="space-y-2">
            <div className="h-2.5 w-12 rounded-full bg-line animate-shimmer" />
            <div className="h-3 rounded-full bg-line animate-shimmer" style={{ width: `${w}%` }} />
            <div className="h-3 w-full rounded-full bg-line animate-shimmer" />
            <div className="h-3 rounded-full bg-line animate-shimmer" style={{ width: `${w - 15}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Empty ──────────────────────────────────────────────────────────────────────
function PanelEmpty({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col h-full">
      <PanelHeader onClose={onClose} />
      <div className="flex-1 flex items-center justify-center px-6">
        <p className="text-[12px] text-ink-3 text-center leading-relaxed">
          Không thể tải nội dung điều luật.<br />
          <span className="opacity-60">Vui lòng thử lại.</span>
        </p>
      </div>
    </div>
  );
}

// ── Shared header ──────────────────────────────────────────────────────────────
function PanelHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between h-[52px] px-5 border-b border-line flex-shrink-0">
      <span className="font-mono text-[10px] tracking-[0.09em] uppercase text-ink-3 select-none">
        Nguồn trích dẫn
      </span>
      <button
        onClick={onClose}
        aria-label="Đóng"
        className="w-7 h-7 rounded-md flex items-center justify-center text-ink-2
                   border border-transparent transition-all duration-150
                   hover:border-line hover:bg-bg-2 hover:text-ink-1 active:scale-95"
      >
        <IconX className="w-[10px] h-[10px]" />
      </button>
    </div>
  );
}

// ── Panel content ──────────────────────────────────────────────────────────────
interface PanelContentProps {
  article:        DieuRecord;
  activeCitation: Citation | null;
  onNavigate:     (id: string) => void;
  onClose:        () => void;
}

function PanelContent({ article, activeCitation, onNavigate, onClose }: PanelContentProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const khoanRefs = useRef<(HTMLDivElement | null)[]>([]);

  // ── Matching khoản logic ─────────────────────────────────────────────────
  // Priority 1: so_khoan directly from LLM (exact)
  // Priority 2: snippet word-overlap fallback
  const matchingKhoanIdx = useMemo(() => {
    // Layer 1: LLM-provided so_khoan (1-indexed → array index = so_khoan - 1)
    if (activeCitation?.so_khoan && activeCitation.so_khoan > 0) {
      const targetNum = `Khoản ${activeCitation.so_khoan}`;
      const idx = article.khoans.findIndex(k => k.num === targetNum);
      if (idx >= 0) return idx;
      // Fallback direct: so_khoan is 1-indexed
      const direct = activeCitation.so_khoan - 1;
      if (direct >= 0 && direct < article.khoans.length) return direct;
    }

    // Layer 2: snippet overlap
    if (!activeCitation?.snippet) return -1;
    const snippet = activeCitation.snippet.toLowerCase();
    let bestScore = 0, bestIdx = -1;
    article.khoans.forEach((k, i) => {
      const text  = k.text.toLowerCase();
      const words = snippet.split(/\s+/).filter(w => w.length > 4);
      if (words.length === 0) return;
      const matches = words.filter(w => text.includes(w)).length;
      const score   = matches / words.length;
      if (score > bestScore && score > 0.3) { bestScore = score; bestIdx = i; }
    });
    return bestIdx;
  }, [article, activeCitation]);

  useEffect(() => {
    if (matchingKhoanIdx >= 0 && khoanRefs.current[matchingKhoanIdx]) {
      setTimeout(() => {
        khoanRefs.current[matchingKhoanIdx]?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 200);
    } else {
      setTimeout(() => { scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" }); }, 120);
    }
  }, [article.id, matchingKhoanIdx]);

  return (
    <div key={article.id} className="flex flex-col h-full animate-fade-up">
      <PanelHeader onClose={onClose} />

      {/* Article identity */}
      <div className="px-5 pt-5 pb-4 border-b border-line flex-shrink-0">
        <p className="font-serif text-2xl italic text-gold leading-tight tracking-[-0.01em] mb-1.5">
          {article.num}
        </p>
        <p className="text-[13px] text-ink-0 leading-[1.55] font-medium">{article.title}</p>
        <div className="flex items-center gap-1.5 mt-3">
          <MetaTag>{article.chuong}</MetaTag>
          <MetaTag>BLLĐ 2012</MetaTag>
        </div>
      </div>

      {/* Khoản body */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-none">
        {article.khoans.length === 0 ? (
          <p className="px-5 py-5 text-body text-ink-3 italic">Không có nội dung chi tiết.</p>
        ) : (
          article.khoans.map((k, i) => {
            const isHighlighted = i === matchingKhoanIdx;
            const khoansWithDiem = k as typeof k & { diem?: DiemData[] };
            return (
              <div
                key={k.num}
                ref={el => { khoanRefs.current[i] = el; }}
                className={[
                  "relative flex gap-0 transition-colors duration-300",
                  i < article.khoans.length - 1 ? "border-b border-line" : "",
                ].join(" ")}
              >
                {/* Left highlight rail */}
                <div
                  className="w-[2px] flex-shrink-0 self-stretch transition-all duration-300 rounded-r-full"
                  style={{
                    background: "rgba(184,144,106,0.35)",
                    opacity:    isHighlighted ? 1 : 0,
                    marginRight: "14px",
                  }}
                />
                <div
                  className="flex-1 py-4 pr-5 transition-colors duration-300"
                  style={{ background: isHighlighted ? "rgba(184,144,106,0.035)" : "transparent" }}
                >
                  {/* Khoản header */}
                  <div className="flex items-center gap-2 mb-2">
                    <p className="font-mono text-[10px] uppercase tracking-[0.07em] text-ink-3">
                      {k.num}
                    </p>
                    {isHighlighted && (
                      <span className="font-mono text-[9px] tracking-[0.06em] uppercase text-gold
                                       bg-gold-dim border border-gold-border rounded-xs px-1.5 py-[2px]">
                        Trích dẫn
                      </span>
                    )}
                  </div>

                  {/* Khoản main text */}
                  <p className={[
                    "text-body leading-[1.72] transition-colors duration-300",
                    isHighlighted ? "text-ink-0" : "text-ink-1",
                  ].join(" ")}>
                    {k.text}
                  </p>

                  {/* Điểm sub-items — rendered when available */}
                  {khoansWithDiem.diem && khoansWithDiem.diem.length > 0 && (
                    <div className="mt-3 space-y-2 pl-3 border-l border-line-2">
                      {khoansWithDiem.diem.map((d, di) => (
                        <div key={di} className="flex gap-2.5">
                          <span className="font-mono text-[9.5px] text-ink-3 flex-shrink-0 pt-[2px] uppercase tracking-[0.06em]">
                            {d.ky_hieu})
                          </span>
                          <p className={[
                            "text-[12.5px] leading-[1.70]",
                            isHighlighted ? "text-ink-1" : "text-ink-2",
                          ].join(" ")}>
                            {d.noi_dung}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Related articles */}
      {article.related.length > 0 && (
        <div className="px-5 py-4 border-t border-line flex-shrink-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3 mb-2.5 select-none">
            Điều liên quan
          </p>
          <div className="flex flex-wrap gap-1.5">
            {article.related.map(relId => {
              const isActive = relId === article.id;
              return (
                <button
                  key={relId}
                  onClick={() => !isActive && onNavigate(relId)}
                  disabled={isActive}
                  className={[
                    "font-mono text-[10.5px] px-2.5 py-1 rounded-md border transition-all duration-150",
                    isActive
                      ? "border-gold-border bg-gold-dim text-gold cursor-default"
                      : "border-line text-ink-2 hover:border-line-2 hover:text-ink-1 hover:bg-bg-2 active:scale-95 cursor-pointer",
                  ].join(" ")}
                >
                  {formatArticleId(relId)}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] px-2 py-[3px] rounded-xs border border-line bg-bg-2 text-ink-2">
      {children}
    </span>
  );
}
