"""
ConflictResolver v1
===================
- Sort chunks theo thu_tu_uu_tien (Luật=1 > NĐ=2 > TT=3)
- Detect conflict: cùng chủ đề, khác loại văn bản → inject conflict note
- Return: (sorted_chunks, conflict_notes)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular import


PRIORITY_LABEL = {
    "luat":       ("Luật", 1),
    "nghi-dinh":  ("Nghị định", 2),
    "thong-tu":   ("Thông tư", 3),
    "quyet-dinh": ("Quyết định", 3),
    "unknown":    ("Không rõ", 4),
}

CONFLICT_NOTE_TEMPLATE = (
    "⚠️ **Lưu ý xung đột pháp lý**: Có {n} văn bản quy định về nội dung này. "
    "Theo nguyên tắc phân cấp pháp luật: {hierarchy}. "
    "Nội dung từ văn bản cấp cao hơn (Luật) được ưu tiên áp dụng."
)


@dataclass
class ConflictNote:
    topic_hint: str
    sources: list[str]
    note: str


def sort_by_priority(chunks: list) -> list:
    """Sort chunks by thu_tu_uu_tien ascending (1=Luật highest priority)."""
    def key(c):
        # Support both dataclass and dict
        prio = getattr(c, "thu_tu_uu_tien", None)
        if prio is None and isinstance(c, dict):
            prio = c.get("thu_tu_uu_tien", 4)
        return prio or 4
    return sorted(chunks, key=key)


def detect_conflicts(chunks: list) -> list[ConflictNote]:
    """
    Detect potential conflicts: same Điều topic, different loai_van_ban.
    Simple heuristic: group by so_dieu cluster, check if multiple loai present.
    """
    # Group by law_type present in results
    types_present: set[str] = set()
    law_sources: list[str] = []

    for c in chunks:
        loai = getattr(c, "loai_van_ban", None) or (c.get("loai_van_ban") if isinstance(c, dict) else None) or "unknown"
        types_present.add(loai)
        law_id = getattr(c, "law_id", None) or (c.get("law_id") if isinstance(c, dict) else None) or ""
        so_hieu = getattr(c, "so_hieu", None) or (c.get("so_hieu") if isinstance(c, dict) else None) or law_id
        if so_hieu and so_hieu not in law_sources:
            law_sources.append(so_hieu)

    if len(types_present) < 2:
        return []  # no conflict

    # Build hierarchy description
    present_sorted = sorted(
        [PRIORITY_LABEL.get(t, ("Không rõ", 4)) for t in types_present],
        key=lambda x: x[1],
    )
    hierarchy = " > ".join(label for label, _ in present_sorted)

    note = CONFLICT_NOTE_TEMPLATE.format(
        n=len(law_sources),
        hierarchy=hierarchy,
    )

    return [ConflictNote(
        topic_hint="mixed_law_types",
        sources=law_sources,
        note=note,
    )]


def resolve(chunks: list) -> tuple[list, list[ConflictNote]]:
    """
    Main entry: sort + detect conflicts.
    Returns (sorted_chunks, conflict_notes).
    """
    sorted_chunks = sort_by_priority(chunks)
    conflicts = detect_conflicts(sorted_chunks)
    return sorted_chunks, conflicts


# ── Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    from dataclasses import dataclass as dc

    @dc
    class FakeChunk:
        chunk_id: str
        loai_van_ban: str
        thu_tu_uu_tien: int
        law_id: str
        so_hieu: str = ""

    chunks = [
        FakeChunk("tt_001", "thong-tu", 3, "lao-dong", "TT 01/2014"),
        FakeChunk("luat_001", "luat", 1, "lao-dong", "10/2012/QH13"),
        FakeChunk("nd_001", "nghi-dinh", 2, "lao-dong", "ND 05/2015"),
    ]

    sorted_c, conflicts = resolve(chunks)
    print("Sorted order:", [c.chunk_id for c in sorted_c])
    for n in conflicts:
        print("Conflict note:", n.note[:100])
