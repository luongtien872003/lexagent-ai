// ─────────────────────────────────────────────
//  Core domain types for LexAgent
// ─────────────────────────────────────────────

// ── Citations ─────────────────────────────────
export type CitationColor = "amber" | "green" | "blue" | "purple";

export interface Citation {
  id:            string;       // e.g. "d38"
  label:         string;       // "Điều 38 — Quyền đơn phương…"
  num:           string;       // "1" — superscript numeral
  color:         CitationColor;
  snippet?:      string;       // law text snippet for hover tooltip preview
  chuong_label?: string;       // e.g. "Chương IV — HỢP ĐỒNG LAO ĐỘNG"
  so_khoan?:     number;       // exact clause number from LLM (0 = whole article)
}

// ── Structured answer types ───────────────────
export interface AnswerSection {
  title:            string;
  bullets:          string[];
  citation_ids:     number[];               // integer so_dieu values
  citation_khoans?: Record<string, number>; // {so_dieu: so_khoan} from LLM
}

export interface StructuredAnswer {
  summary:  string;
  sections: AnswerSection[];
}

// ── Message content ───────────────────────────
export type ContentBlock =
  | { type: "text";  text: string       }
  | { type: "bold";  text: string       }
  | { type: "break"                     }
  | { type: "cite";  citation: Citation };

export interface UserMessage {
  role: "user";
  id:   string;
  text: string;
}

export interface AssistantMessage {
  role:       "assistant";
  id:         string;
  content:    ContentBlock[];
  citations:  Citation[];
  structured: StructuredAnswer | null;
}

export type Message = UserMessage | AssistantMessage;

// ── Conversations ─────────────────────────────
export interface Conversation {
  id:        string;
  title:     string;
  createdAt: string;          // ISO-8601
  messages:  Message[];
}

// ── Legal document ────────────────────────────
export interface Diem {
  ky_hieu: string;  // "a", "b", "c"
  noi_dung: string;
}

export interface Khoan {
  num:   string;    // "Khoản 1"
  text:  string;
  diem?: Diem[];   // sub-items điểm a, b, c
}

export interface DieuRecord {
  id:      string;            // "d38"
  num:     string;            // "Điều 38"
  title:   string;
  chuong:  string;            // "Chương IV"
  khoans:  Khoan[];
  related: string[];          // sibling IDs
}

// ── Model tiers ──────────────────────────────────
export type ModelTierId = "fast" | "balanced" | "precise";

export interface ModelTier {
  id:          ModelTierId;
  name:        string;
  description: string;
  cost_vnd:    number;
}

export const MODEL_TIERS: ModelTier[] = [
  { id: "fast",     name: "Nhanh",     description: "Câu hỏi đơn giản",  cost_vnd: 50  },
  { id: "balanced", name: "Cân bằng",  description: "Phân tích tốt hơn", cost_vnd: 130 },
  { id: "precise",  name: "Chính xác", description: "Pháp lý phức tạp",  cost_vnd: 700 },
];

// ── Pipeline / Streaming ──────────────────────
export type StepStatus  = "pending" | "active" | "done";
export type StreamPhase = "thinking" | "streaming" | "done";

export interface StepChild {
  label:  string;   // e.g. "BM25 → 8 kết quả"
  meta?:  string;   // top-3 results, multiline
  done:   boolean;
}

export interface PipelineStep {
  id:          string;        // backend step key: classifying | retrieving | reranking | generating
  instanceKey: string;        // unique per row
  label:       string;        // Vietnamese display label
  status:      StepStatus;
  detail?:     string;        // current running detail
  meta?:       string;        // expandable content (sub-queries, articles found, verdict)
  children:    StepChild[];   // sub-steps shown as tree (BM25, E5, BGE, RRF, Rerank)
}

// ── Streaming state ───────────────────────────
export interface StreamState {
  phase:    StreamPhase;
  steps:    PipelineStep[];
  text:     string;
  sections: AnswerSection[];
}

// ── Citation hover state ──────────────────────
// Centralized in useChat so all surfaces (inline, chip, panel) sync.
export interface CitationHoverState {
  id:      string | null;     // which citation is hovered
  // Anchor rect for tooltip positioning (set by the triggering element)
  anchorRect: DOMRect | null;
}
