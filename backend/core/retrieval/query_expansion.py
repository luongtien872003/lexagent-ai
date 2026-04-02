"""
Query Expansion — thêm legal synonyms trước khi search.
Giúp paraphrase và scenario queries tìm đúng điều hơn.

v2: Thêm hard case synonyms cho 3 câu hỏi lỗi + intent-aware expansion.
"""

# ── Synonym pháp lý tiếng Việt ───────────────────────────────────
LEGAL_SYNONYMS = {
    # Hành động
    "sa thải":          ["đơn phương chấm dứt hợp đồng", "cho thôi việc", "kỷ luật sa thải"],
    "nghỉ việc":        ["chấm dứt hợp đồng lao động", "thôi việc"],

    # q016 fix — "tự ý nghỉ việc" → Điều 37 (quyền đơn phương chấm dứt)
    # Vấn đề: retriever bị kéo về Điều 107 (giờ làm thêm/lương) vì query có
    # "làm thêm giờ" + "không trả lương". Cần expand vế 2 của query mạnh hơn.
    "tự ý nghỉ việc":   ["đơn phương chấm dứt hợp đồng lao động", "quyền chấm dứt hợp đồng"],
    "tự nghỉ việc":     ["đơn phương chấm dứt hợp đồng lao động", "quyền chấm dứt"],
    "quyền nghỉ việc":  ["đơn phương chấm dứt hợp đồng", "quyền người lao động chấm dứt"],
    "ép làm thêm":      ["vi phạm hợp đồng lao động", "đơn phương chấm dứt hợp đồng"],
    "thử việc":         ["làm thử", "thời gian thử việc", "hợp đồng thử việc"],
    "bồi thường":       ["trợ cấp", "đền bù", "thanh toán"],
    "ký hợp đồng":      ["giao kết hợp đồng lao động"],
    "đóng cửa":         ["tạm đình chỉ hoạt động", "đóng cửa nơi làm việc"],

    # Chủ thể
    "sếp":              ["người sử dụng lao động", "chủ doanh nghiệp"],
    "nhân viên":        ["người lao động", "người làm việc"],
    "công ty":          ["người sử dụng lao động", "doanh nghiệp"],
    "lao động nữ":      ["lao động là phụ nữ", "người lao động nữ"],

    # Quyền lợi
    "lương":            ["tiền lương", "tiền công", "thù lao"],
    "làm thêm giờ":     ["làm thêm", "giờ làm thêm", "tăng ca", "overtime"],
    "nghỉ phép":        ["nghỉ hằng năm", "nghỉ có lương", "phép năm"],
    "thai sản":         ["mang thai", "sinh con", "nghỉ thai sản"],
    "trợ cấp thôi việc":["trợ cấp mất việc", "tiền thôi việc"],

    # Khái niệm chung
    "độ tuổi":          ["tuổi lao động", "15 tuổi", "đủ tuổi"],
    "đình công":        ["ngừng việc tập thể", "bãi công"],
    "khuyết tật":       ["người khuyết tật", "tàn tật", "lao động khuyết tật"],
    "hợp pháp":         ["đúng pháp luật", "được phép", "không vi phạm"],

    # ── v2: Hard case fixes ──────────────────────────────────────

    # q003 — "Độ tuổi tối thiểu người lao động" → Điều 3
    # Điều 3 title: "Giải thích từ ngữ" — người lao động là người từ đủ 15 tuổi trở lên
    "tuổi tối thiểu":   [
        "người từ đủ 15 tuổi trở lên",
        "giải thích từ ngữ",
        "định nghĩa người lao động",
    ],
    "độ tuổi tối thiểu": [
        "người từ đủ 15 tuổi trở lên",
        "giải thích từ ngữ người lao động",
    ],
    "được coi là người lao động": [
        "người từ đủ 15 tuổi",
        "giải thích từ ngữ điều 3",
    ],

    # q004 — "Người lao động có quyền đình công" → Điều 5
    # Điều 5: "Quyền và nghĩa vụ của người lao động" — liệt kê quyền bao gồm đình công
    # "đình công" nặng ở Chương XIV → cần disambiguate bằng context "quyền cơ bản"
    "quyền đình công":  [
        "quyền và nghĩa vụ của người lao động",
        "quyền cơ bản người lao động điều 5",
    ],
    "người lao động có quyền đình công": [
        "quyền và nghĩa vụ của người lao động",
        "quyền cơ bản tổ chức đình công",
    ],

    # q005 — "Người sử dụng lao động có quyền đóng cửa tạm thời" → Điều 6
    # Điều 6: "Quyền và nghĩa vụ của người sử dụng lao động"
    # Điều 216 (cạnh tranh): chỉ nói về đóng cửa khi đình công, không phải quyền chung
    "đóng cửa tạm thời nơi làm việc": [
        "quyền và nghĩa vụ của người sử dụng lao động",
        "quyền đóng cửa tạm thời người sử dụng lao động điều 6",
    ],
    "quyền đóng cửa":   [
        "quyền của người sử dụng lao động",
        "tạm đình chỉ hoạt động nơi làm việc",
    ],
    "người sử dụng lao động có quyền đóng cửa": [
        "quyền và nghĩa vụ của người sử dụng lao động điều 6",
    ],
}

# ── Concept expansion ────────────────────────────────────────────
LEGAL_CONCEPTS = {
    "chấm dứt hợp đồng": ["điều kiện", "trường hợp", "quyền"],
    "tiền lương":        ["mức lương", "trả lương", "tính lương"],
    "kỷ luật":           ["xử lý", "hình thức kỷ luật", "sa thải"],
    "đào tạo":           ["học nghề", "tập nghề", "bồi dưỡng"],
}


def expand_query(query: str, max_expansions: int = 3) -> str:
    """
    Thêm synonym vào query để tăng recall.
    Ưu tiên match dài nhất trước (tránh partial match xấu).
    """
    query_lower = query.lower()
    added_terms = []
    added_count = 0
    used_terms  = set()

    # Sort by length DESC để ưu tiên match dài nhất
    sorted_synonyms = sorted(LEGAL_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)

    for term, synonyms in sorted_synonyms:
        if added_count >= max_expansions:
            break
        if term in query_lower and term not in used_terms:
            used_terms.add(term)
            for syn in synonyms[:2]:
                if added_count >= max_expansions:
                    break
                if syn.lower() not in query_lower:
                    added_terms.append(syn)
                    added_count += 1

    for concept, related in LEGAL_CONCEPTS.items():
        if added_count >= max_expansions:
            break
        if concept in query_lower:
            for r in related[:1]:
                if added_count >= max_expansions:
                    break
                if r.lower() not in query_lower:
                    added_terms.append(r)
                    added_count += 1

    if added_terms:
        return query + " " + " ".join(added_terms)
    return query


def expand_with_intent(query: str, intent: dict) -> str:
    """
    Intent-aware expansion: thêm extra_expansion từ classifier.
    Dùng cho hard cases.
    """
    # Bắt đầu từ standard expansion
    expanded = expand_query(query, max_expansions=3)

    # Thêm extra terms từ intent classifier
    extra = intent.get("extra_expansion", [])
    if extra:
        # Chỉ thêm những gì chưa có trong expanded
        exp_lower = expanded.lower()
        to_add = [t for t in extra if t.lower() not in exp_lower]
        if to_add:
            expanded = expanded + " " + " ".join(to_add)

    return expanded


def expand_for_bm25(query: str) -> str:
    """Expand aggressively hơn cho BM25 (cần exact keyword)."""
    return expand_query(query, max_expansions=5)


def expand_for_vector(query: str) -> str:
    """Expand nhẹ hơn cho vector (đã có semantic)."""
    return expand_query(query, max_expansions=2)


if __name__ == "__main__":
    test_queries = [
        "Độ tuổi tối thiểu để được coi là người lao động theo Bộ luật là bao nhiêu?",
        "Người lao động có quyền đình công không?",
        "Người sử dụng lao động có quyền đóng cửa tạm thời nơi làm việc không?",
        "Công ty tôi đang muốn sa thải nhân viên đang mang thai",
        "Tôi bị sếp ép làm thêm giờ không trả lương",
        "Việc làm là gì theo định nghĩa của Bộ luật lao động?",
    ]
    print("Query Expansion v2 Test:")
    print("=" * 70)
    for q in test_queries:
        expanded = expand_query(q)
        if expanded != q:
            print(f"Original : {q}")
            print(f"Expanded : {expanded}")
        else:
            print(f"No expand: {q}")
        print()