"""
LawClassifier v1 — keyword-based, zero LLM.
Phát hiện câu hỏi thuộc luật nào trong 6 bộ luật target.

Trả về: list[str] — law_ids theo thứ tự ưu tiên (empty = tất cả)
"""
from __future__ import annotations
import re

# ── Keyword registry ────────────────────────────────────────
_LAW_KEYWORDS: dict[str, list[str]] = {
    "lao-dong": [
        "lao động", "người lao động", "hợp đồng lao động", "tiền lương",
        "lương tối thiểu", "thử việc", "sa thải", "thôi việc", "nghỉ phép",
        "phép năm", "làm thêm giờ", "tăng ca", "đình công", "kỷ luật",
        "người sử dụng lao động", "hsdl", "người nsdlđ",
        "chấm dứt hợp đồng", "tai nạn lao động", "bệnh nghề nghiệp",
        "thời giờ làm việc", "nghỉ ngơi", "thai sản lao động",
    ],
    "bhxh": [
        "bảo hiểm xã hội", "bhxh", "lương hưu", "hưu trí",
        "ốm đau", "thai sản", "tai nạn lao động bảo hiểm",
        "bệnh nghề nghiệp bảo hiểm", "tử tuất", "trợ cấp một lần",
        "đóng bảo hiểm", "mức đóng bhxh",
    ],
    "bhyt": [
        "bảo hiểm y tế", "bhyt", "khám chữa bệnh", "bảo hiểm sức khỏe",
        "thẻ bhyt", "thanh toán bhyt", "cùng chi trả",
        "cơ sở khám chữa bệnh", "viện phí",
    ],
    "viec-lam": [
        "việc làm", "thất nghiệp", "bảo hiểm thất nghiệp",
        "trợ cấp thất nghiệp", "giải quyết việc làm",
        "giới thiệu việc làm", "trung tâm việc làm",
        "lao động nước ngoài", "xuất khẩu lao động",
    ],
    "an-toan-lao-dong": [
        "an toàn lao động", "vệ sinh lao động", "bảo hộ lao động",
        "an toàn vệ sinh", "phòng cháy", "thiết bị an toàn",
        "môi trường lao động", "độc hại", "nguy hiểm",
    ],
    "cong-doan": [
        "công đoàn", "tổ chức công đoàn", "công đoàn cơ sở",
        "ban chấp hành công đoàn", "đại diện công đoàn",
        "thương lượng tập thể", "thỏa ước lao động tập thể",
    ],
}

# Precompile
_COMPILED: dict[str, list[re.Pattern]] = {
    law_id: [re.compile(re.escape(kw), re.IGNORECASE) for kw in kws]
    for law_id, kws in _LAW_KEYWORDS.items()
}


def classify_laws(query: str) -> list[str]:
    """
    Trả về list law_ids theo thứ tự điểm số giảm dần.
    Empty list = không xác định được, nên search tất cả.
    """
    scores: dict[str, int] = {}
    for law_id, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.search(query):
                scores[law_id] = scores.get(law_id, 0) + 1

    if not scores:
        return []

    # Sort by score desc
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Chỉ trả về các luật có điểm >= max_score/2 (tránh noise)
    max_score = ranked[0][1]
    return [law_id for law_id, score in ranked if score >= max(1, max_score // 2)]


# ── Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ("Người lao động bị sa thải có được nhận trợ cấp không?", ["lao-dong"]),
        ("Mức đóng BHXH năm 2024 là bao nhiêu?", ["bhxh"]),
        ("Thẻ BHYT được thanh toán những loại thuốc nào?", ["bhyt"]),
        ("Công đoàn có quyền gì trong thương lượng tập thể?", ["cong-doan"]),
        ("Xin chào", []),
    ]
    ok = 0
    for q, expected in cases:
        result = classify_laws(q)
        status = "✅" if (set(result) & set(expected) or (not expected and not result)) else "❌"
        if status == "✅": ok += 1
        print(f"{status} '{q[:50]}' → {result} (expected: {expected})")
    print(f"\n{ok}/{len(cases)} correct")
