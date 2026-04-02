"""
Verifier Agent v3 — fixed loop + dead-end detection
"""

import json
from dataclasses import dataclass
from openai import OpenAI
from backend.core.retrieval.reranker import RerankResult

VERIFY_SYSTEM = """Bạn là chuyên gia đánh giá tính đầy đủ thông tin pháp luật lao động.

NGUYÊN TẮC: BLLĐ không có điều riêng cho từng scenario — Điều 38, 48 là điều CHUNG.
Nếu đã có điều luật CHUNG bao phủ vấn đề → sufficient=true, KHÔNG tìm thêm.

sufficient=TRUE khi:
✓ Đã có điều luật về quyền/nghĩa vụ liên quan câu hỏi
✓ Đã có công thức/mức tính (dù chưa có số liệu cụ thể của user)
✓ Chỉ thiếu dữ liệu user (số năm, lương) — KHÔNG tìm thêm

sufficient=FALSE chỉ khi thiếu hẳn điều luật về vấn đề pháp lý MỚI chưa có.

JSON:
{"sufficient": true/false, "missing": "vấn đề pháp lý mới thiếu", "follow_up": "query tìm điều luật mới"}"""

_SUFFICIENT_COMBOS = [
    # Dissolution / termination + severance
    {47, 48},   # thời hạn thanh toán + trợ cấp thôi việc (giải thể, đơn phương)
    {38, 48},   # sa thải + trợ cấp thôi việc
    {37, 38},   # quyền NLĐ + quyền NSDLĐ đơn phương chấm dứt
    # Restructuring — MUST have Điều 44 or 45
    {44, 49},   # cắt giảm kinh tế + trợ cấp mất việc
    {45, 49},   # sáp nhập/chia tách + trợ cấp mất việc
    # Tranh chấp / dispute
    {200, 48},  # giải quyết tranh chấp + trợ cấp thôi việc
    {200, 49},  # giải quyết tranh chấp + trợ cấp mất việc
    # Maternity
    {155, 42},
    # Wrongful termination
    {42, 43},
]

_DEAD_END_SIGNALS = [
    "thời gian làm việc thực tế", "số năm làm việc",
    "mức lương cụ thể", "lương của nhân viên",
    "trường hợp sa thải do", "ốm đau kéo dài",
    "quy định riêng cho", "điều luật riêng",
    "điều 38",
    "trợ cấp thôi việc cụ thể", "thông tin cá nhân",
]


@dataclass
class VerifyResult:
    sufficient: bool
    missing:    str
    follow_up:  str


def verify_context(client: OpenAI, query: str, chunks: list[RerankResult]) -> VerifyResult:
    if not chunks:
        return VerifyResult(False, "Không tìm được điều luật nào", query)

    found = {c.so_dieu for c in chunks}

    # Layer 1: known-sufficient combination → skip LLM entirely
    for combo in _SUFFICIENT_COMBOS:
        if combo.issubset(found):
            print(f"[Verifier] Combo {combo} found → sufficient, skip LLM")
            return VerifyResult(True, "", "")

    context_text = "".join(
        f"Điều {c.so_dieu}. {c.ten_dieu}\n{c.noi_dung[:800]}\n\n"
        for c in chunks
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VERIFY_SYSTEM},
                {"role": "user",   "content": f"Câu hỏi: {query}\n\nĐiều luật:\n{context_text}"},
            ],
            temperature=0.0, max_tokens=200,
            response_format={"type": "json_object"},
        )
        r = json.loads(resp.choices[0].message.content)
        sufficient = r.get("sufficient", True)
        missing    = r.get("missing", "")
        follow_up  = r.get("follow_up", "")

        # Layer 2: dead-end signal → override
        if not sufficient and follow_up:
            fu = follow_up.lower()
            if any(s in fu for s in _DEAD_END_SIGNALS):
                print(f"[Verifier] Dead-end: {follow_up[:60]} → override sufficient=True")
                return VerifyResult(True, "", "")

        return VerifyResult(sufficient, missing, follow_up)

    except Exception as e:
        print(f"[Verifier] Error: {e} → assume sufficient")
        return VerifyResult(True, "", "")
