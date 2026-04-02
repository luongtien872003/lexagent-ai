"""
TemporalFilter v1
=================
Detect thời gian trong query → build Qdrant filter tương ứng.

Patterns:
- "trước năm 2013" → filter ngay_hieu_luc < 2013-01-01
- "sau 2015" / "từ 2016" → ngay_hieu_luc >= 2016-01-01
- "hiện hành" / "hiện tại" → lấy văn bản mới nhất (sort by date desc)
- "năm 2012" → exact year range
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class TemporalContext:
    has_temporal: bool = False
    filter_type: str = ""         # "before" | "after" | "year" | "latest"
    year: int = 0
    note: str = ""
    qdrant_filter: dict = field(default_factory=dict)


_RE_BEFORE = re.compile(r'tr[ưướ]c\s+(?:n[aă]m\s+)?(\d{4})', re.IGNORECASE)
_RE_AFTER  = re.compile(r'(?:sau|t[ừư]|k[eể]\s*t[ừư])\s+(?:n[aă]m\s+)?(\d{4})', re.IGNORECASE)
_RE_YEAR   = re.compile(r'n[aă]m\s+(\d{4})', re.IGNORECASE)
_RE_LATEST = re.compile(r'hi[eệ]n\s*(?:h[aà]nh|t[aạ]i|nay)|m[oớ]i\s*nh[aấ]t|hi[eệ]u\s*l[uự]c\s*hi[eệ]n', re.IGNORECASE)


def detect_temporal(query: str) -> TemporalContext:
    ctx = TemporalContext()

    # "hiện hành" / "mới nhất"
    if _RE_LATEST.search(query):
        ctx.has_temporal = True
        ctx.filter_type = "latest"
        ctx.note = "Lọc văn bản đang hiệu lực / mới nhất"
        ctx.qdrant_filter = {}  # handled by sort in retriever
        return ctx

    # "trước năm YYYY"
    m = _RE_BEFORE.search(query)
    if m:
        year = int(m.group(1))
        ctx.has_temporal = True
        ctx.filter_type = "before"
        ctx.year = year
        ctx.note = f"Lọc văn bản trước năm {year}"
        ctx.qdrant_filter = _build_date_filter("lt", f"{year}-01-01")
        return ctx

    # "sau/từ năm YYYY"
    m = _RE_AFTER.search(query)
    if m:
        year = int(m.group(1))
        ctx.has_temporal = True
        ctx.filter_type = "after"
        ctx.year = year
        ctx.note = f"Lọc văn bản từ năm {year} trở đi"
        ctx.qdrant_filter = _build_date_filter("gte", f"{year}-01-01")
        return ctx

    # "năm YYYY" (exact)
    m = _RE_YEAR.search(query)
    if m:
        year = int(m.group(1))
        ctx.has_temporal = True
        ctx.filter_type = "year"
        ctx.year = year
        ctx.note = f"Lọc văn bản năm {year}"
        ctx.qdrant_filter = _build_date_range_filter(year)
        return ctx

    return ctx


def _build_date_filter(op: str, date_str: str) -> dict:
    """Qdrant range filter on ngay_hieu_luc (stored as string YYYY-MM-DD)."""
    return {
        "must": [{
            "key": "ngay_hieu_luc",
            "range": {op: date_str}
        }]
    }


def _build_date_range_filter(year: int) -> dict:
    return {
        "must": [{
            "key": "ngay_hieu_luc",
            "range": {
                "gte": f"{year}-01-01",
                "lt": f"{year + 1}-01-01",
            }
        }]
    }


def apply_temporal_filter_to_chunks(chunks: list, ctx: TemporalContext) -> list:
    """
    Post-filter for BM25 (which can't use Qdrant filters).
    Filter by ngay_hieu_luc field in chunk metadata.
    """
    if not ctx.has_temporal:
        return chunks

    def get_year(c) -> int:
        date_str = getattr(c, "ngay_hieu_luc", "") or ""
        if not date_str:
            return 0
        try:
            return int(date_str[:4])
        except Exception:
            return 0

    if ctx.filter_type == "before":
        return [c for c in chunks if 0 < get_year(c) < ctx.year]
    elif ctx.filter_type in ("after",):
        return [c for c in chunks if get_year(c) >= ctx.year]
    elif ctx.filter_type == "year":
        return [c for c in chunks if get_year(c) == ctx.year]
    elif ctx.filter_type == "latest":
        # Sort by year desc, keep all (let retriever decide top_k)
        return sorted(chunks, key=lambda c: get_year(c), reverse=True)
    return chunks


# ── Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        "Quy định về thai sản trước năm 2013",
        "Mức lương tối thiểu từ năm 2020",
        "Chính sách BHXH hiện hành",
        "Luật lao động năm 2012 điều chỉnh gì",
        "Người lao động có quyền gì?",
    ]
    for q in cases:
        ctx = detect_temporal(q)
        print(f"  '{q[:50]}' → has={ctx.has_temporal}, type={ctx.filter_type}, year={ctx.year}")
