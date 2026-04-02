"""
Query Intent Classifier
-----------------------
Phát hiện loại query để điều chỉnh retrieval strategy.

Key insight: 3 hard cases (q003, q004, q005) đều hỏi về quyền cơ bản / định nghĩa
nằm ở Chương I (Điều 1-10). Classifier phát hiện pattern này → boost early chapters.
"""

import re

# ── Tín hiệu định nghĩa / khái niệm ─────────────────────────────
DEFINITION_SIGNALS = [
    "là gì", "định nghĩa", "khái niệm", "được hiểu là",
    "giải thích", "theo bộ luật là", "có nghĩa là",
    "được coi là", "được xác định là",
]

# ── Tín hiệu hỏi về quyền cơ bản (Chương I) ────────────────────
BASIC_RIGHTS_SIGNALS = [
    "có quyền", "có được phép", "có bị cấm",
    "được phép không", "có hợp pháp không",
    "có được làm", "có được hưởng",
    "quyền gì", "những quyền nào",
]

# ── Tín hiệu phạm vi áp dụng ────────────────────────────────────
COVERAGE_SIGNALS = [
    "áp dụng cho", "đối tượng nào", "ai được áp dụng",
    "điều chỉnh", "phạm vi áp dụng", "đối tượng điều chỉnh",
]

# ── Tín hiệu scenario / tình huống ──────────────────────────────
SCENARIO_SIGNALS = [
    "tôi bị", "anh a", "chị b", "công ty tôi", "doanh nghiệp tôi",
    "nhân viên tôi", "bị ốm", "bị sa thải", "bị đuổi",
    "tôi muốn", "tôi đang", "trường hợp của tôi",
    "có được sa thải không", "có được nghỉ không",
]

# ── Hard cases cụ thể — target trực tiếp 3 câu hỏi lỗi ─────────
HARD_CASE_MAP = {
    # q003: Điều 3 — định nghĩa người lao động, 15 tuổi
    "minimum_age": {
        "signals": [
            "tuổi tối thiểu", "độ tuổi tối thiểu", "bao nhiêu tuổi",
            "đủ tuổi lao động", "người lao động là người",
            "được coi là người lao động",
        ],
        "boost_dieu_range": (1, 15),
        "extra_expansion": [
            "người từ đủ 15 tuổi trở lên",
            "giải thích từ ngữ",
            "định nghĩa người lao động",
        ],
    },
    # q004: Điều 5 — quyền cơ bản người lao động (bao gồm đình công)
    "basic_worker_right": {
        "signals": [
            "người lao động có quyền đình công",
            "quyền đình công",
            "được đình công không",
            "có quyền tổ chức đình công",
        ],
        "boost_dieu_range": (1, 15),
        "extra_expansion": [
            "quyền và nghĩa vụ của người lao động",
            "quyền cơ bản người lao động",
            "tổ chức đình công",
        ],
    },
    # q005: Điều 6 — quyền người sử dụng lao động (đóng cửa)
    "lockout_right": {
        "signals": [
            "đóng cửa tạm thời nơi làm việc",
            "quyền đóng cửa",
            "người sử dụng lao động có quyền đóng cửa",
            "tạm thời đóng cửa",
        ],
        "boost_dieu_range": (1, 15),
        "extra_expansion": [
            "quyền và nghĩa vụ của người sử dụng lao động",
            "quyền đóng cửa nơi làm việc",
            "tạm đình chỉ hoạt động",
        ],
    },
}


def classify_query(query: str) -> dict:
    """
    Phân loại intent của query.

    Returns:
        {
            "type":              str   — "definition" | "basic_rights" | "coverage" | "scenario" | "general"
            "boost_early":       bool  — True nếu nên boost Điều 1-20
            "hard_case":         str | None  — tên hard case nếu match
            "priority_chapters": list[int]   — danh sách chương ưu tiên
            "boost_dieu_range":  tuple | None — (min, max) điều cần boost
            "extra_expansion":   list[str]   — từ khoá bổ sung cho expansion
        }
    """
    q_lower = query.lower().strip()

    # 1. Kiểm tra hard cases trước (priority cao nhất)
    for case_name, case_cfg in HARD_CASE_MAP.items():
        if any(sig in q_lower for sig in case_cfg["signals"]):
            return {
                "type":              "basic_rights",
                "boost_early":       True,
                "hard_case":         case_name,
                "priority_chapters": [1],
                "boost_dieu_range":  case_cfg["boost_dieu_range"],
                "extra_expansion":   case_cfg["extra_expansion"],
            }

    # 2. Định nghĩa / khái niệm
    if any(sig in q_lower for sig in DEFINITION_SIGNALS):
        return {
            "type":              "definition",
            "boost_early":       True,
            "hard_case":         None,
            "priority_chapters": [1],
            "boost_dieu_range":  (1, 20),
            "extra_expansion":   [],
        }

    # 3. Quyền cơ bản (chưa phải hard case)
    if any(sig in q_lower for sig in BASIC_RIGHTS_SIGNALS):
        return {
            "type":              "basic_rights",
            "boost_early":       True,
            "hard_case":         None,
            "priority_chapters": [1],
            "boost_dieu_range":  (1, 20),
            "extra_expansion":   [],
        }

    # 4. Phạm vi áp dụng
    if any(sig in q_lower for sig in COVERAGE_SIGNALS):
        return {
            "type":              "coverage",
            "boost_early":       True,
            "hard_case":         None,
            "priority_chapters": [1],
            "boost_dieu_range":  (1, 5),
            "extra_expansion":   [],
        }

    # 5. Scenario — KHÔNG boost early
    if any(sig in q_lower for sig in SCENARIO_SIGNALS):
        return {
            "type":              "scenario",
            "boost_early":       False,
            "hard_case":         None,
            "priority_chapters": [],
            "boost_dieu_range":  None,
            "extra_expansion":   [],
        }

    # 6. General
    return {
        "type":              "general",
        "boost_early":       False,
        "hard_case":         None,
        "priority_chapters": [],
        "boost_dieu_range":  None,
        "extra_expansion":   [],
    }


if __name__ == "__main__":
    test_cases = [
        # 3 hard cases
        ("q003", "Độ tuổi tối thiểu để được coi là người lao động theo Bộ luật là bao nhiêu?"),
        ("q004", "Người lao động có quyền đình công không?"),
        ("q005", "Người sử dụng lao động có quyền đóng cửa tạm thời nơi làm việc không?"),
        # Others
        ("q001", "Bộ luật lao động điều chỉnh những vấn đề gì?"),
        ("q007", "Việc làm là gì theo định nghĩa của Bộ luật lao động?"),
        ("q015", "Công ty tôi đang muốn sa thải nhân viên đang mang thai. Điều này có hợp pháp không?"),
        ("q016", "Tôi bị sếp ép làm thêm giờ không trả lương, tôi có quyền tự ý nghỉ việc không?"),
    ]

    print("Query Classifier Test")
    print("=" * 70)
    for qid, q in test_cases:
        result = classify_query(q)
        print(f"\n[{qid}] {q[:60]}...")
        print(f"  type={result['type']} | boost_early={result['boost_early']} | hard_case={result['hard_case']}")
        if result["extra_expansion"]:
            print(f"  extra_expansion={result['extra_expansion']}")
        if result["boost_dieu_range"]:
            print(f"  boost_dieu_range={result['boost_dieu_range']}")
