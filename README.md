# LexAgent — Hệ thống RAG Pháp luật Lao động Việt Nam

> **Trợ lý AI** chuyên tư vấn pháp luật lao động và bảo hiểm xã hội Việt Nam.  
> Kiến trúc: **Agentic RAG** với hybrid retrieval (BM25 + E5 + BGE + Reranker) và streaming SSE.

---

## Mục lục

1. [Tổng quan kiến trúc](#tổng-quan-kiến-trúc)
2. [Data Pipeline](#data-pipeline)
3. [Backend — Cấu trúc chi tiết](#backend)
4. [Frontend — Cấu trúc chi tiết](#frontend)
5. [Scripts & Tools](#scripts--tools)
6. [Crawler](#crawler)
7. [Extractor](#extractor)
8. [Data](#data)
9. [Docker](#docker)
10. [Eval](#eval)
11. [Luồng dữ liệu end-to-end](#luồng-dữ-liệu-end-to-end)
12. [Quan hệ phụ thuộc giữa các file](#quan-hệ-phụ-thuộc-giữa-các-file)
13. [Cài đặt & Chạy](#cài-đặt--chạy)
14. [Thêm bộ luật mới](#thêm-bộ-luật-mới)
15. [Trạng thái hiện tại](#trạng-thái-hiện-tại)

---

## Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER BROWSER                               │
│                    Next.js (port 3000)                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / SSE (EventSource)
┌────────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend (port 8000)                      │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────────────────────────────┐   │
│  │   Routers    │   │           PipelineService                │   │
│  │  /health     │   │                                          │   │
│  │  /convs      │──▶│  1. LawClassifier → law_ids             │   │
│  │  /documents  │   │  2. QueryDecomposer → sub-queries        │   │
│  └──────────────┘   │  3. BM25 + E5 + BGE → candidates        │   │
│                     │  4. Reranker → top-3                     │   │
│                     │  5. Verifier → đủ chưa?                 │   │
│                     │  6. ContextBuilder → prompt              │   │
│                     │  7. GPT-4o-mini → answer (stream SSE)   │   │
│                     └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
         │              │                    │
    ┌────▼───┐    ┌─────▼──────┐    ┌───────▼────────┐
    │  BM25  │    │   Qdrant   │    │   OpenAI API   │
    │  .pkl  │    │ (E5 + BGE) │    │  GPT-4o-mini   │
    └────────┘    └────────────┘    └────────────────┘
```

---

## Data Pipeline

Quy trình xử lý dữ liệu từ nguồn đến index:

```
.doc (tvpl.vn)
    │
    ▼ scripts/extract_doc.py  (LibreOffice convert)
.txt (UTF-8 plain text)
    │
    ▼ scripts/doc_extractor.py  (regex parser)
.json (chunks: điều + khoản + metadata)
    │
    ├──▶ scripts/index_bm25.py  →  data/indexes/bm25_<law>.pkl
    │
    └──▶ backend/core/indexing/vector_indexer.py  →  Qdrant Cloud
              ├── dense_e5  (multilingual-e5-large, 1024d)
              ├── dense_bge (BAAI/bge-m3, 1024d)
              └── sparse_bge (bge-m3 sparse/IDF)
```

**Thống kê dữ liệu hiện tại:**

| Bộ luật | Điều | Khoản | File |
|---|---|---|---|
| Bộ luật Lao động 2019 | 220 | 644 | lao-dong.json |
| Bộ luật Lao động 2012 | 242 | 629 | lao-dong-2012.json |
| Luật BHXH 2014 | 125 | 404 | bhxh.json |
| Luật BHYT sửa đổi 2014 | 2 | 57 | bhyt.json |
| Luật Việc làm 2013 | 62 | 171 | viec-lam.json |
| Luật ATVSLĐ 2015 | 93 | 358 | an-toan-lao-dong.json |
| Luật Công đoàn 2012 | 33 | 89 | cong-doan.json |
| **TỔNG** | **777** | **2352** | |

---

## Backend

### `backend/app/main.py`
**Entry point** của FastAPI. Khởi động `lifespan` context:
- Tạo `DocumentService` (load JSON extractor)
- Tạo `ConversationService` (in-memory store)
- Spawn background task `PipelineService.initialize()` — load tất cả ML models
- Mount 3 router: `health`, `conversations`, `documents`
- Config CORS cho frontend `localhost:3000`

**Phụ thuộc:** `config.py`, `services/`, tất cả routers

---

### `backend/app/config.py`
**Cấu hình tập trung** — tất cả path và env vars đều lấy từ đây:
- Qdrant URL/key/collection name
- Đường dẫn đến BM25 indexes, extracted JSONs, KG files
- LLM model tiers (`fast=gpt-4o-mini`, `balanced=gpt-4.1-mini`, `precise=gpt-4o`)
- Hàm `get_model(tier)`, `get_max_tokens(tier)`
- CORS origins

> ⚠️ Mọi file khác đều import từ đây, **không hard-code path** ở nơi khác.

---

### `backend/app/schemas.py`
**Pydantic models** cho request/response API:
- `CreateConversationRequest`, `SendMessageRequest`
- `Citation` — điều, khoản, snippet được trả về frontend
- `StructuredSection` — `{title, bullets[], citation_ids[], citation_khoans{}}`
- `StructuredAnswer` — `{summary, sections[]}`
- `MessageResponse` — có `structured` field cho frontend render
- SSE event types: `SSEStatusEvent`, `SSETokenEvent`, `SSESectionsEvent`, `SSEDoneEvent`, `SSEErrorEvent`

> Schema `StructuredSection` phải **khớp chính xác** với `SYSTEM_PROMPT` trong `context_builder.py` và types trong `frontend/lib/types.ts`.

---

### `backend/app/routers/conversations.py`
Router xử lý toàn bộ luồng chat:
- `POST /api/conversations` — tạo conversation mới
- `GET /api/conversations` — list conversations
- `POST /api/conversations/{id}/messages` — gửi tin nhắn (stream SSE)

**Luồng streaming:**
1. Nhận message từ user
2. Gọi `pipeline_service.query_stream()`
3. Emit SSE events: `status` → `sections` → `token` → `done`
4. Save message vào `ConversationService`

---

### `backend/app/routers/documents.py`
- `GET /api/documents` — list tất cả điều luật
- `GET /api/documents/{id}` — lấy nội dung 1 điều (cho Source Panel)

**Phụ thuộc:** `DocumentService`

---

### `backend/app/routers/health.py`
- `GET /api/health` — trả về `{status: "ready"/"loading", uptime, models_loaded}`

Frontend poll endpoint này để biết models đã load xong chưa.

---

## backend/core/

### `backend/core/retrieval/base.py`
Định nghĩa **`RetrievedChunk`** dataclass — unit dữ liệu cơ bản đi xuyên suốt pipeline:

```python
@dataclass
class RetrievedChunk:
    chunk_id, so_dieu, ten_dieu, chuong_so, ten_chuong,
    noi_dung, score, source,
    # v2 multi-law fields:
    law_id, khoan_so, loai_van_ban, thu_tu_uu_tien,
    ngay_hieu_luc, context_header, parent_dieu_id, so_hieu
```

Cũng định nghĩa `BaseRetriever` ABC với method `search(query, top_k, law_ids)`.

> Tất cả retrievers đều trả `list[RetrievedChunk]`. **Đây là contract trung tâm của retrieval layer.**

---

### `backend/core/retrieval/bm25.py`
**BM25 Retriever v2** — keyword-based, không cần GPU:
- Load nhiều `.pkl` files cùng lúc (multi-law)
- `BM25Retriever(index_dir)` — scan tất cả `bm25_*.pkl` trong thư mục
- `.search(query, top_k, law_ids=None)` — filter theo law_ids nếu có
- Tokenize bằng `underthesea` (nếu có) hoặc whitespace

**Input:** `data/indexes/bm25_*.pkl`  
**Output:** `list[RetrievedChunk]`

---

### `backend/core/retrieval/vector.py`
**Vector Retrievers** — semantic search qua Qdrant:
- `VectorRetriever` — dense search (E5 hoặc BGE)
- `BGESparseRetriever` — sparse lexical search (bge-m3 sparse)
- Hỗ trợ Qdrant filter theo `law_id`, `ngay_hieu_luc`
- Prefix `"query: "` cho E5, không prefix cho BGE

**Input:** Qdrant collection `legal_vn_v2`  
**Output:** `list[RetrievedChunk]`

---

### `backend/core/retrieval/fusion.py`
**Weighted RRF** (Reciprocal Rank Fusion):
- `weighted_rrf(results_with_weights, top_k)` — merge nhiều result lists
- `chapter_boost_rerank(results, boost_dieu_range, boost_factor)` — boost điều thuộc chương ưu tiên
- `intent_aware_rrf(...)` — kết hợp fusion + boost dựa trên intent

**Công thức:** `score(d) = Σ weight_i / (k + rank_i(d))`

Weights mặc định:
- BM25: 0.3–0.5 (yếu hơn với corpus lớn)
- E5: 1.5–2.0
- BGE dense: 2.0
- BGE sparse: 0.8–1.0

---

### `backend/core/retrieval/reranker.py`
**BGE Reranker** — cross-encoder scoring:
- Model: `BAAI/bge-reranker-v2-m3`
- Input: query + top-15 chunks từ fusion
- Output: `list[RerankResult]` sorted theo `hybrid_score`
- `hybrid_score = alpha * rerank_score + (1-alpha) * rrf_score`
- Intent-aware prefix: thêm context vào query trước khi rerank

---

### `backend/core/retrieval/query_classifier.py`
Phân loại intent của query để chọn retrieval strategy:
- `basic_rights` / `definition` / `coverage` → boost E5, boost early chapters
- `scenario` / `procedure` → boost BGE dense
- `multi_hop` → giữ nguyên weights

Trả về `{type, boost_early, boost_dieu_range}`.

---

### `backend/core/retrieval/query_expansion.py`
Mở rộng query với synonym pháp lý tiếng Việt:
- `"sa thải"` → thêm `"đơn phương chấm dứt hợp đồng"`, `"cho thôi việc"`
- `"đình công"` → thêm `"ngừng việc tập thể"`
- `expand_with_intent(query, intent)` — chọn expansion strategy theo intent

---

### `backend/core/retrieval/kg_retriever.py`
**Knowledge Graph Retriever** — graph-based retrieval:
- Load `citation_graph_*.json` — quan hệ tham chiếu giữa các điều
- Expand kết quả: Điều 37 → tham chiếu → Điều 38, 39
- `get_triples_for_chunks(chunks)` — lấy triple facts cho context

---

### `backend/core/retrieval/graph_retriever.py`
Graph traversal retriever — mở rộng kết quả theo đồ thị tham chiếu (dự phòng cho KG retriever).

---

### `backend/core/law/classifier.py`
**LawClassifier** — keyword-based, zero LLM call:
- `classify_laws(query) → list[str]` — trả law_ids theo điểm số
- 6 bộ luật được đăng ký với keyword lists: lao-dong, bhxh, bhyt, viec-lam, an-toan-lao-dong, cong-doan
- Query "sa thải" → `["lao-dong"]`
- Query "đóng BHXH" → `["bhxh"]`
- Query không rõ → `[]` (search tất cả)

> **law_ids từ classifier được pass xuống TẤT CẢ sub-queries** trong agentic pipeline — đây là điểm then chốt của multi-law support.

---

### `backend/core/law/conflict.py`
**ConflictResolver** — xử lý xung đột pháp lý:
- `resolve(chunks) → (sorted_chunks, conflict_notes)`
- Sort theo `thu_tu_uu_tien`: Luật=1 > Nghị định=2 > Thông tư=3
- Detect conflict khi có nhiều loại văn bản cho cùng chủ đề
- Inject conflict note vào context: *"⚠️ Luật > Nghị định > Thông tư"*

---

### `backend/core/law/temporal.py`
**TemporalFilter** — phát hiện context thời gian trong query:
- `detect_temporal(query) → TemporalContext`
- "trước năm 2013" → filter `ngay_hieu_luc < 2013-01-01`
- "hiện hành" / "mới nhất" → sort by date desc
- "từ năm 2020" → filter `ngay_hieu_luc >= 2020-01-01`
- Trả về Qdrant filter dict cho vector search

---

### `backend/core/pipeline/context_builder.py`
**ContextBuilder** — build prompt cho LLM:
- `build_context(chunks, query, ...)` → `ContextResult` với `.prompt`
- Hỗ trợ cả `chunks=` (v3 style) và `reranked=` (pipeline_service style)
- Inject conflict notes nếu có
- Truncate chunks để không vượt token limit
- Include KG triples (optional)
- Include conversation history (4 turns gần nhất)

**`SYSTEM_PROMPT`** — quan trọng nhất:
- Ra lệnh LLM trả về JSON đúng schema `{summary, sections[{title, bullets[], citation_ids[], citation_khoans{}}]}`
- Giải thích hệ thống phân cấp pháp luật
- Bắt buộc trích dẫn số điều, khoản

**`parse_structured_answer(raw)`** — parse JSON response từ LLM:
- Rescue logic nếu JSON bị truncate
- Fallback về `{summary: raw, sections: []}` nếu không parse được

---

### `backend/core/pipeline/decomposer.py`
**QueryDecomposer** — tách câu hỏi phức tạp thành sub-queries:
- Gọi `gpt-4o-mini` (1 lần, cheapest)
- Domain knowledge về Bộ luật → sub-queries có thuật ngữ pháp lý chính xác
- Ví dụ: "Thôi việc được những gì?" → ["trợ cấp thôi việc Điều 48", "điều kiện nhận trợ cấp"]

---

### `backend/core/pipeline/verifier.py`
**Verifier** — kiểm tra context đã đủ chưa:
- Gọi `gpt-4o-mini` với query + top-5 chunks
- Trả về `{sufficient: bool, missing: str, follow_up: str}`
- Nếu chưa đủ → `follow_up` query để search thêm (tối đa `MAX_AGENTIC_ROUNDS=3`)

---

### `backend/core/pipeline/agentic.py`
**Agentic Pipeline** — orchestration logic thuần (không có async/SSE):
- `run_pipeline(query, bm25, reranker, client) → dict`
- Bước 1: `classify_laws` → `law_ids`
- Bước 2: `detect_temporal` → `temporal_ctx`
- Bước 3: `decompose_query` → `sub_queries`
- Bước 4: Với mỗi sub-query: retrieve (BM25 + Vector) → rerank
- Bước 5: `conflict_resolve` → sort + conflict notes
- Bước 6: `verify_context` → loop nếu chưa đủ
- Bước 7: `build_context` → prompt → LLM → answer

---

### `backend/core/indexing/bm25_indexer.py`
CLI tool build BM25 index từ extracted JSON:
- `BM25Okapi(corpus, k1=1.5, b=0.75)`
- Prefer khoản-level chunks (granular hơn)
- Output: `data/indexes/bm25_{law_id}.pkl`

---

### `backend/core/indexing/vector_indexer.py`
CLI tool index vectors lên Qdrant:
- Index khoản-level + dieu-level chunks
- Point ID = `hash(chunk_id)` — tránh conflict khi multi-law
- Payload đầy đủ v3: 17 fields bao gồm `law_id`, `khoan_so`, `loai_van_ban`...
- `--skip-e5` / `--skip-bge` để index từng model riêng

---

### `backend/core/indexing/qdrant_setup.py`
Tạo Qdrant collection với:
- 3 vector spaces: `dense_e5` (1024d), `dense_bge` (1024d), `sparse_bge` (IDF)
- 11 payload indexes để filter nhanh: `law_id`, `so_dieu`, `khoan_so`, `loai_van_ban`, `thu_tu_uu_tien`, `ngay_hieu_luc`...

---

### `backend/core/indexing/kg_builder.py`
Build Knowledge Graph từ extracted JSON — phân tích tham chiếu giữa các điều luật.

---

### `backend/services/pipeline_service.py`
**Glue layer** giữa FastAPI và core logic (~800 dòng):
- `initialize()` — load tất cả models trong background thread (không block event loop)
- `query_stream(...)` — async streaming với SSE callbacks
- `_retrieve_progressive_stream(...)` — emit status từng bước BM25 → E5 → BGE → RRF → Rerank
- `_chitchat_response(...)` — fast path cho greetings, không trigger retrieval
- `_build_citations(reranked, structured)` — map citations từ LLM output về chunks
- Tất cả blocking calls được wrap trong `asyncio.run_in_executor`

**Callbacks:**
- `on_status(step, detail, meta, is_new_step)` → SSE `status` event
- `on_token(text)` → SSE `token` event  
- `on_sections(sections[])` → SSE `sections` event

---

### `backend/services/conversation_service.py`
In-memory store cho conversations và messages:
- `dict[conv_id, Conversation]`
- `Conversation.messages: list[Message]`
- Không persist — restart server = mất lịch sử

> ⚠️ Cần thay bằng database (SQLite/PostgreSQL) cho production thật sự.

---

### `backend/services/document_service.py`
Load extracted JSON để serve cho `/api/documents`:
- Parse `chunks` → `dict[so_dieu, DieuData]`
- Hỗ trợ lookup theo `chunk_id` cho Source Panel

---

## Frontend

### `frontend/app/page.tsx`
Root component — render `ChatWindow` + `Sidebar` + `SourcePanel`.

### `frontend/app/layout.tsx`
Next.js layout — font, metadata, global providers.

### `frontend/app/globals.css`
CSS variables, animations (`shimmer`, `fade-up`, `blink`), Tailwind base.

---

### `frontend/lib/types.ts`
**Toàn bộ TypeScript types** — source of truth cho frontend:
- `RetrievedChunk`, `Citation`, `AnswerSection`, `StructuredAnswer`
- `PipelineStep`, `StepChild`, `StreamPhase`, `StreamState`
- `ModelTier`, `ModelTierId`
- `Message`, `Conversation`, `DieuRecord`, `Khoan`

> Phải **sync với `backend/app/schemas.py`** — nếu backend thêm field, frontend phải cập nhật ở đây.

---

### `frontend/lib/hooks/useChat.ts`
**Core hook** (~350 dòng) — quản lý toàn bộ chat state:
- Manage `conversations`, `activeConvId`, `streamState`
- `submitMessage(text)` → POST → parse SSE stream
- Parse events: `status` → update pipeline steps, `sections` → pre-render, `token` → streaming text, `done` → finalize
- Handle model tier selection
- Error recovery

**SSE parsing logic:**
```
EventSource → status events → build PipelineStep tree
                            → sections arrive before tokens
                            → tokens stream summary text
                            → done → convert to AssistantMessage
```

---

### `frontend/lib/hooks/useCitationHover.ts`
Global citation hover state — sync giữa inline citation chips, tooltip, và Source Panel.

### `frontend/lib/hooks/useScrollToBottom.ts`
Auto-scroll khi message mới đến.

---

### `frontend/components/chat/ChatWindow.tsx`
Container chính — render danh sách messages, handle scroll.

### `frontend/components/chat/ChatInput.tsx`
Input box + model tier selector + submit button.

### `frontend/components/chat/ChatTopbar.tsx`
Topbar với conversation title và controls.

### `frontend/components/chat/EmptyState.tsx`
Màn hình trống khi chưa có tin nhắn — hiện suggested questions.

---

### `frontend/components/chat/message/StreamingMessage.tsx`
**Real-time message** đang stream:
- `ThinkingBlock` — collapsible pipeline steps với timer
- `StepLine` — 1 step (classifying/retrieving/reranking/generating)
- `ChildRow` — sub-step trong tree (BM25, E5, BGE, RRF, Rerank)
- `SectionSkeletons` — skeleton loading cho sections
- `StreamingText` — text đang stream với cursor blink

### `frontend/components/chat/message/AssistantMessage.tsx`
**Completed message** — render `StructuredAnswer` + citations.

### `frontend/components/chat/message/StructuredAnswer.tsx`
Render sections: heading + bullets + citation chips.

### `frontend/components/chat/message/CitationChip.tsx`
Badge `[1]`, `[2]`... hover để xem snippet.

### `frontend/components/chat/message/CitationTooltip.tsx`
Tooltip khi hover citation chip — hiện điều, khoản, snippet.

### `frontend/components/chat/message/ContentRenderer.tsx`
Parse raw text → `ContentBlock[]` (text, bold, cite, break) để render inline.

### `frontend/components/chat/message/UserMessage.tsx`
Render user message bubble.

### `frontend/components/chat/message/AgentLabel.tsx`
"LexAgent" label với pulsing dot khi streaming.

---

### `frontend/components/sidebar/Sidebar.tsx`
Danh sách conversations + new conversation button.

### `frontend/components/source-panel/SourcePanel.tsx`
Panel bên phải — hiện full text của điều luật được cite.

---

## Scripts & Tools

### `scripts/doc_extractor.py`
**Parser** từ plain text (LibreOffice output) → JSON chunks:
- State machine: Chương → Điều → body lines → khoản
- Regex: `^Điều\s+(\d+)[.\-\s]` để detect điều
- Parse khoản: `^(\d+)\.\s+(.+)` sequential numbering
- Output JSON schema: `{document, chunks[], graph_edges[]}`

Mỗi chunk có:
```json
{
  "id": "lao-dong_dieu_037_khoan_1",
  "type": "khoan",
  "so_dieu": 37, "khoan_so": 1,
  "law_id": "lao-dong",
  "loai_van_ban": "luat",
  "context_header": "Bộ luật Lao động > Chương III > Điều 37 > Khoản 1",
  "text_for_bm25": "...",
  "text_for_embedding": "passage: ..."
}
```

---

### `scripts/extract_doc.py`
**Pipeline wrapper** cho extraction:
1. Tìm LibreOffice (`soffice.exe`) trên máy
2. Convert `.doc` → `.txt` (UTF-8) vào temp dir
3. Gọi `doc_extractor.py` để parse `.txt` → `.json`
4. Save vào `data/extracted/<law_id>/<law_id>.json`

Tự detect LibreOffice path trên Windows/Linux/Mac.

---

### `scripts/index_bm25.py`
Build BM25 indexes từ tất cả JSONs trong `data/extracted/`:
- Prefer khoản-level chunks
- Filter chunks có `noi_dung < 30 chars` (noise)
- Output: `data/indexes/bm25_<law_id>.pkl`

---

### `scripts/setup_qdrant.py`
Tạo Qdrant collection `legal_vn_v2` với 11 payload indexes.

---

### `scripts/crawl.py`
Wrapper gọi `crawler/tvpl_crawler.py`.

---

## Crawler

### `crawler/tvpl_crawler.py`
Async crawler cho thuvienphapluat.vn:
- Rate-limited (2s giữa các request)
- Tự detect bị block (response < 10KB)
- Kiểm tra nội dung có `Điều X` thật không
- Save raw bytes (không decode để tránh encoding lỗi)

### `crawler/registry.yaml`
Config 7 bộ luật: URL, law_id, ngay_hieu_luc, loai_van_ban.

> ⚠️ tvpl.vn thường block crawler nếu không đăng nhập. Khuyến nghị tải `.doc` thủ công từ tvpl → dùng `extract_doc.py`.

---

## Extractor

### `extractor/main.go`
Go extractor v2 (legacy — dùng cho HTML từ moj.gov.vn):
- Parse HTML theo anchor `<a name="dieu_X">`, `<a name="chuong_X">`
- 1 chunk = 1 khoản (granular)
- Output JSON với đầy đủ metadata v3

> Hiện tại pipeline chính dùng `doc_extractor.py` (Python). Go extractor giữ lại cho HTML từ moj.gov.vn.

---

## Data

```
data/
├── raw/                    ← HTML/DOC gốc từ crawler
│   └── <law_id>/
│       └── <law_id>.doc
├── extracted/              ← JSON chunks sau khi extract
│   └── <law_id>/
│       └── <law_id>.json   ← Input cho BM25 + Vector indexer
├── indexes/                ← BM25 pickle files
│   └── bm25_<law_id>.pkl   ← Load bởi BM25Retriever
└── html/                   ← HTML gốc (legacy)
```

---

## Docker

### `docker/backend.Dockerfile`
- Base: `python:3.11-slim`
- Copy `backend/`, `data/indexes/`, `extractor/output/`
- `CMD: uvicorn backend.app.main:app`

### `docker/frontend.Dockerfile`
- Multi-stage: builder (npm build) → runner (node standalone)
- `CMD: node server.js`

### `docker-compose.yml`
- `backend` (port 8000) + `frontend` (port 3000)
- `frontend depends_on backend` với healthcheck
- Volume mount `./data` để persist indexes

---

## Eval

### `eval/questions.json`
20 câu hỏi test: exact, paraphrase, scenario, multi_hop.

### `eval/eval_bm25.py`
Quick eval BM25 only — Recall@1, Recall@5 trên 20 câu.

### `eval/eval_v2.py` → `eval_v6.py`
Các phiên bản eval trước đó (historical). `eval_v6.py` là mới nhất.

---

## Luồng dữ liệu end-to-end

```
User: "Người lao động đơn phương chấm dứt HĐLĐ cần báo trước bao lâu?"
    │
    ▼  useChat.ts → POST /api/conversations/{id}/messages
    │
    ▼  conversations.py → pipeline_service.query_stream()
    │
    ├─ law/classifier.py → ["lao-dong"]         (keyword match)
    ├─ law/temporal.py   → no temporal context
    ├─ pipeline/decomposer.py → ["báo trước chấm dứt HĐLĐ Điều 37"]
    │
    ▼  retrieval/
    ├─ bm25.py.search("báo trước...", law_ids=["lao-dong"])  → 10 chunks
    ├─ vector.py E5.search(..., filter=law_id=lao-dong)      → 10 chunks
    ├─ vector.py BGE.search(...)                             → 10 chunks
    ├─ vector.py BGESparse.search(...)                       → 10 chunks
    │
    ▼  fusion.py.weighted_rrf(...)    → top-15 merged
    ▼  reranker.py.rerank(...)        → top-3 (Điều 37 Khoản 2, 3...)
    │
    ▼  pipeline/verifier.py           → {sufficient: true}
    ▼  law/conflict.py.resolve(...)   → sorted, no conflict
    │
    ▼  pipeline/context_builder.py    → prompt với Điều 37 content
    │
    ▼  OpenAI GPT-4o-mini             → JSON stream
    │  {summary: "...", sections: [{title: "Thời hạn", bullets: [...]}]}
    │
    ▼  SSE events:
    ├─ status: "classifying..." → "retrieving BM25..." → "generating..."
    ├─ sections: [{title, bullets, citation_ids: [37]}]
    └─ token: "Theo Điều 37..." (word-by-word)
    │
    ▼  StreamingMessage.tsx → ThinkingBlock + SectionSkeletons + StreamingText
    ▼  AssistantMessage.tsx → StructuredAnswer + CitationChips
    ▼  SourcePanel.tsx      → full text Điều 37 Khoản 2
```

---

## Quan hệ phụ thuộc giữa các file

```
backend/app/main.py
    └── backend/app/config.py              (paths, env vars)
    └── backend/services/pipeline_service.py
            └── backend/core/retrieval/bm25.py
            │       └── backend/core/retrieval/base.py (RetrievedChunk)
            │       └── data/indexes/bm25_*.pkl
            └── backend/core/retrieval/vector.py
            │       └── Qdrant Cloud
            └── backend/core/retrieval/reranker.py
            └── backend/core/retrieval/fusion.py
            │       └── backend/core/retrieval/base.py
            └── backend/core/retrieval/query_classifier.py
            └── backend/core/retrieval/query_expansion.py
            └── backend/core/law/classifier.py   → law_ids filter
            └── backend/core/law/conflict.py      → sort + notes
            └── backend/core/law/temporal.py      → date filter
            └── backend/core/pipeline/decomposer.py → sub-queries
            └── backend/core/pipeline/verifier.py   → sufficiency check
            └── backend/core/pipeline/context_builder.py → prompt
                    └── SYSTEM_PROMPT (JSON schema cho LLM)
    └── backend/services/conversation_service.py  (in-memory)
    └── backend/services/document_service.py
            └── data/extracted/*/  (JSON chunks)
    └── backend/app/routers/conversations.py
            └── backend/app/schemas.py  (SSE event types)
    └── backend/app/routers/documents.py
    └── backend/app/routers/health.py

scripts/extract_doc.py
    └── LibreOffice (soffice.exe)
    └── scripts/doc_extractor.py
            └── data/extracted/<law_id>/<law_id>.json

scripts/index_bm25.py
    └── data/extracted/**/*.json
    └── data/indexes/bm25_*.pkl

backend/core/indexing/vector_indexer.py
    └── data/extracted/**/*.json
    └── Qdrant Cloud (legal_vn_v2)

frontend/lib/hooks/useChat.ts
    └── /api/conversations (SSE)
    └── frontend/lib/types.ts

frontend/components/chat/message/StreamingMessage.tsx
    └── frontend/lib/types.ts (PipelineStep, AnswerSection)

frontend/components/source-panel/SourcePanel.tsx
    └── /api/documents/{id}
```

---

## Cài đặt & Chạy

### Requirements
- Python 3.11+
- Node.js 20+
- LibreOffice (để extract .doc)
- Qdrant Cloud account (free tier OK)
- OpenAI API key

### Backend

```bash
# 1. Tạo venv
python -m venv venv
.\venv\Scripts\activate      # Windows
source venv/bin/activate     # Linux/Mac

# 2. Cài dependencies
pip install -r backend/requirements.txt

# 3. Config
cp .env.example .env
# Điền: OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY

# 4. Extract data (cần file .doc từ tvpl.vn)
python scripts/extract_doc.py --file "data/raw/lao-dong/Bo-Luat-lao-dong-2019.doc" \
    --law-id lao-dong --so-hieu "45/2019/QH14" --hieu-luc 2021-01-01
# ... repeat for tất cả 7 luật

# 5. Index BM25
python scripts/index_bm25.py

# 6. Setup Qdrant + Index vectors
python scripts/setup_qdrant.py
python backend/core/indexing/vector_indexer.py --input data/extracted/lao-dong/lao-dong.json

# 7. Chạy
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Docker (production)

```bash
cp .env.example .env   # điền keys
docker compose up --build -d
```

---

## Thêm bộ luật mới

1. Tải `.doc` từ thuvienphapluat.vn (cần đăng nhập)
2. Đặt vào `data/raw/<law_id>/`
3. Extract:
   ```bash
   python scripts/extract_doc.py \
       --file data/raw/<law_id>/<file>.doc \
       --law-id <law_id> \
       --so-hieu "XX/YYYY/QHZZ" \
       --hieu-luc YYYY-MM-DD
   ```
4. Index BM25: `python scripts/index_bm25.py`
5. Index vector: `python backend/core/indexing/vector_indexer.py --input data/extracted/<law_id>/<law_id>.json`
6. Thêm keywords vào `backend/core/law/classifier.py` để LawClassifier nhận diện được
7. Thêm entry vào `crawler/registry.yaml`

---

## Trạng thái hiện tại

### ✅ Hoạt động
- Full pipeline: BM25 + E5 + BGE + Reranker + GPT-4o-mini
- 777 điều / 2352 khoản từ 7 bộ luật
- Streaming SSE với thinking steps
- Citation đến level khoản
- Multi-law routing (LawClassifier)
- Conflict resolution (Luật > NĐ > TT)
- Conversation history (in-memory)

### ⚠️ Hạn chế
- BM25 dùng whitespace tokenizer (thiếu `underthesea`) — -15% accuracy
- Conversation không persist khi restart server
- bhyt chỉ có luật sửa đổi (2 điều), thiếu full text gốc
- Không có auth / rate limiting

### 🔮 Roadmap
- Thêm `underthesea` tokenizer
- SQLite persistence cho conversations
- Auth layer
- HTTPS + nginx reverse proxy
- Monitoring (Sentry / Grafana)