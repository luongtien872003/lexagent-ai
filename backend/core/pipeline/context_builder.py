"""
Context Builder v3
==================
- Pack top-K chunks thành context string cho LLM
- SYSTEM_PROMPT ra lệnh LLM trả JSON đúng schema: {summary, sections[{title,bullets,citation_ids,citation_khoans}]}
- build_context() trả ContextResult với .prompt attribute (dùng bởi pipeline_service)
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass

MAX_CHARS_PER_CHUNK = 800
MAX_TOTAL_CHARS     = 6000

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
# Schema khớp với StructuredSection trong api/schemas.py:
#   title: str, bullets: list[str], citation_ids: list[int], citation_khoans: dict

SYSTEM_PROMPT = """Bạn là trợ lý pháp lý chuyên về luật lao động và bảo hiểm xã hội Việt Nam.

## Nguyên tắc
1. Chỉ trả lời dựa trên ngữ cảnh pháp lý được cung cấp. Không suy đoán.
2. Trích dẫn chính xác số điều, khoản.
3. Nếu không có thông tin: nói rõ không tìm thấy.

## Hệ thống phân cấp pháp luật
Khi nhiều văn bản cùng quy định một vấn đề: Luật > Nghị định > Thông tư.

## ĐỊNH DẠNG BẮT BUỘC — JSON THUẦN TÚY, KHÔNG MARKDOWN

Trả lời theo schema sau (không thêm bất kỳ text nào ngoài JSON):

{
  "summary": "<tóm tắt ngắn gọn 1-2 câu, trả lời thẳng vào câu hỏi>",
  "sections": [
    {
      "title": "<tên phần, ví dụ: Căn cứ pháp lý | Điều kiện | Mức hưởng | Thủ tục>",
      "bullets": [
        "<điểm 1 cụ thể, có số liệu nếu có>",
        "<điểm 2>",
        "<điểm 3>"
      ],
      "citation_ids": [<so_dieu_1>, <so_dieu_2>],
      "citation_khoans": {"<so_dieu>": <so_khoan>}
    }
  ]
}

## Hướng dẫn sections
- Luôn có ít nhất 2 sections
- Section 1: "Căn cứ pháp lý" — liệt kê điều luật áp dụng
- Section 2+: nội dung cụ thể (Điều kiện / Mức hưởng / Thủ tục / Lưu ý)
- Mỗi bullet: ngắn gọn, cụ thể, có số liệu/thời hạn khi có
- citation_ids: danh sách so_dieu được trích dẫn trong section này
- citation_khoans: nếu trích dẫn khoản cụ thể, ghi {"<so_dieu>": <so_khoan>}

## Ví dụ output hợp lệ
{
  "summary": "Người lao động có quyền nhận trợ cấp thôi việc sau 12 tháng làm việc, mức 0.5 tháng lương/năm.",
  "sections": [
    {
      "title": "Căn cứ pháp lý",
      "bullets": ["Điều 48 Bộ luật Lao động 10/2012/QH13 — Trợ cấp thôi việc"],
      "citation_ids": [48],
      "citation_khoans": {"48": 1}
    },
    {
      "title": "Điều kiện hưởng",
      "bullets": [
        "Đã làm việc ít nhất 12 tháng liên tục",
        "Hợp đồng chấm dứt theo Điều 36, 37, 38 hoặc 44, 45"
      ],
      "citation_ids": [48],
      "citation_khoans": {}
    },
    {
      "title": "Mức trợ cấp",
      "bullets": [
        "0.5 tháng tiền lương cho mỗi năm làm việc",
        "Tiền lương tính bình quân 6 tháng liền kề trước khi chấm dứt"
      ],
      "citation_ids": [48],
      "citation_khoans": {"48": 2}
    }
  ]
}

Lưu ý: Đây là thông tin tham khảo, không phải tư vấn pháp lý chính thức."""


# ── ContextResult ─────────────────────────────────────────────────────────────

@dataclass
class ContextResult:
    """pipeline_service dùng .prompt để build messages cho LLM."""
    prompt:  str
    context: str


# ── build_context ─────────────────────────────────────────────────────────────

def build_context(
    chunks: list = None,
    conflict_notes: list = None,
    query: str = "",
    # pipeline_service style kwargs
    reranked: list = None,
    kg_retriever=None,
    max_chunks: int = 7,
    max_triples: int = 8,
    conversation_history: list = None,
) -> ContextResult:
    """
    Build context + prompt cho LLM.

    Hỗ trợ 2 cách gọi:
      build_context(chunks, query=q)                               # v3/agentic style
      build_context(query=q, reranked=reranked, kg_retriever=kg)  # pipeline_service style
    """
    effective_chunks = chunks if chunks is not None else (reranked or [])

    if not effective_chunks:
        ctx    = "Không tìm thấy tài liệu liên quan."
        prompt = f"Câu hỏi: {query}\n\nNgữ cảnh pháp lý:\n{ctx}" if query else ctx
        return ContextResult(prompt=prompt, context=ctx)

    parts       = []
    total_chars = 0

    # Conflict notes
    if conflict_notes:
        for note in conflict_notes:
            note_text = getattr(note, "note", str(note))
            parts.append(f"\n{note_text}\n")
            total_chars += len(note_text)

    shown = 0
    for i, chunk in enumerate(effective_chunks[:max_chunks], 1):
        c = getattr(chunk, "chunk", chunk)

        def _get(obj, key, default=""):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        law_id     = _get(c, "law_id",        "") or ""
        loai       = _get(c, "loai_van_ban",   "") or "luat"
        so_hieu    = _get(c, "so_hieu",        "") or law_id or "10/2012/QH13"
        so_dieu    = _get(c, "so_dieu",        0)
        ten_dieu   = _get(c, "ten_dieu",       "") or ""
        khoan_so   = _get(c, "khoan_so",       0)
        noi_dung   = _get(c, "noi_dung",       "") or ""
        ctx_header = _get(c, "context_header", "") or ""

        loai_label = {
            "luat": "Luật", "nghi-dinh": "Nghị định", "thong-tu": "Thông tư"
        }.get(loai, "Văn bản")

        if ctx_header:
            header = f"[{i}] {ctx_header}"
        elif khoan_so:
            header = f"[{i}] {loai_label} {so_hieu} — Điều {so_dieu} Khoản {khoan_so}: {ten_dieu}"
        else:
            header = f"[{i}] {loai_label} {so_hieu} — Điều {so_dieu}: {ten_dieu}"

        body = noi_dung[:MAX_CHARS_PER_CHUNK]
        if len(noi_dung) > MAX_CHARS_PER_CHUNK:
            body += "..."

        chunk_text = f"{header}\n{body}"

        if total_chars + len(chunk_text) > MAX_TOTAL_CHARS:
            remaining = len(effective_chunks) - i
            if remaining > 0:
                parts.append(f"[... còn {remaining} tài liệu không hiển thị]")
            break

        parts.append(chunk_text)
        total_chars += len(chunk_text)
        shown += 1

    # KG triples (optional)
    if kg_retriever and shown > 0:
        try:
            triples = kg_retriever.get_triples_for_chunks(effective_chunks[:shown])
            if triples:
                triple_lines = "\n".join(f"  {t}" for t in triples[:max_triples])
                parts.append(f"\n[Quan hệ pháp lý]\n{triple_lines}")
        except Exception:
            pass

    # Conversation history (optional, last 4 turns)
    history_text = ""
    if conversation_history:
        lines = []
        for msg in conversation_history[-4:]:
            role    = msg.get("role", "")
            content = msg.get("content", "")[:200]
            if role == "user":
                lines.append(f"Người dùng: {content}")
            elif role == "assistant" and content:
                lines.append(f"Trợ lý: {content}")
        if lines:
            history_text = "[Lịch sử hội thoại]\n" + "\n".join(lines) + "\n\n"

    ctx    = "\n\n".join(parts)
    prompt = f"{history_text}Câu hỏi: {query}\n\nNgữ cảnh pháp lý:\n{ctx}" if query else ctx

    return ContextResult(prompt=prompt, context=ctx)


# ── parse_structured_answer ───────────────────────────────────────────────────

def parse_structured_answer(raw: str) -> dict | None:
    """
    Parse JSON response từ LLM → dict với summary + sections.
    Có rescue logic cho truncated JSON.
    """
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        text  = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        text  = text.strip()

    # Attempt 1: parse toàn bộ
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed.setdefault("summary", "")
            parsed.setdefault("sections", [])
            for sec in parsed.get("sections", []):
                sec.setdefault("bullets", [])
                sec.setdefault("citation_ids", [])
                sec.setdefault("citation_khoans", {})
            return parsed
    except Exception:
        pass

    # Attempt 2: extract summary từ truncated JSON
    m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if m:
        return {"summary": m.group(1), "sections": []}

    # Attempt 3: fallback — raw text làm summary
    return {"summary": text, "sections": []}


# ── Test ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from dataclasses import dataclass as dc

    @dc
    class FakeChunk:
        so_dieu:        int = 48
        ten_dieu:       str = "Trợ cấp thôi việc"
        chuong_so:      int = 4
        ten_chuong:     str = "CHẤM DỨT HỢP ĐỒNG"
        noi_dung:       str = "1. Khi hợp đồng lao động chấm dứt... người sử dụng lao động có trách nhiệm trả trợ cấp thôi việc..."
        law_id:         str = "lao-dong"
        khoan_so:       int = 1
        loai_van_ban:   str = "luat"
        so_hieu:        str = "10/2012/QH13"
        context_header: str = "Bộ luật Lao động 2012 > Chương IV > Điều 48 > Khoản 1"

    result = build_context(
        reranked=[FakeChunk(), FakeChunk()],
        query="Điều kiện nhận trợ cấp thôi việc?",
    )
    print("=== prompt (400 chars) ===")
    print(result.prompt[:400])

    sample = '{"summary": "Test OK", "sections": [{"title": "Căn cứ", "bullets": ["Điều 48"], "citation_ids": [48], "citation_khoans": {"48": 1}}]}'
    print("\n=== parsed ===", parse_structured_answer(sample))