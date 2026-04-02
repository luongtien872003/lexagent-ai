"""
BM25 Retriever v2
-----------------
- Load nhiều pkl files theo law_id (multi-law support)
- Search với law_ids filter
- Trả RetrievedChunk v2 với đầy đủ metadata
- Backward compatible với v1 single-pkl
"""
from __future__ import annotations
import pickle
from pathlib import Path
from backend.core.retrieval.base import RetrievedChunk

try:
    from underthesea import word_tokenize
    _USE_UNDERTHESEA = True
except ImportError:
    _USE_UNDERTHESEA = False



def tokenize(text: str) -> list[str]:
    text = text.lower()
    if _USE_UNDERTHESEA:
        tokens = word_tokenize(text, format="text").split()
    else:
        tokens = text.split()
    return [t for t in tokens if len(t) >= 2]


# ── Single-law index ─────────────────────────────────────────
class _BM25Index:
    """Wraps one pkl file."""

    def __init__(self, path: str | Path):
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.bm25   = data["bm25"]
        self.chunks = data["chunks"]  # list of dicts
        self._path  = str(path)

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed[:top_k]:
            c = self.chunks[idx]
            results.append(RetrievedChunk(
                chunk_id       = c.get("id", f"chunk_{idx}"),
                so_dieu        = c.get("so_dieu", 0),
                ten_dieu       = c.get("ten_dieu", ""),
                chuong_so      = c.get("chuong_so", 0),
                ten_chuong     = c.get("ten_chuong", ""),
                noi_dung       = c.get("noi_dung", ""),
                score          = float(score),
                source         = "bm25",
                law_id         = c.get("law_id", "unknown"),
                khoan_so       = c.get("khoan_so", 0),
                loai_van_ban   = c.get("loai_van_ban", "luat"),
                thu_tu_uu_tien = c.get("thu_tu_uu_tien", 1),
                ngay_hieu_luc  = c.get("ngay_hieu_luc", ""),
                context_header = c.get("context_header", ""),
                parent_dieu_id = c.get("parent_dieu_id", ""),
                so_hieu        = c.get("so_hieu", ""),
            ))
        return results


# ── Multi-law BM25Retriever ───────────────────────────────────
class BM25Retriever:
    """
    Load một hoặc nhiều pkl files.
    Nếu init_path là thư mục, auto-load tất cả *.pkl bên trong.
    Nếu init_path là file, load single pkl (backward compat).
    """

    def __init__(self, index_path: str | Path):
        path = Path(index_path)
        self._indexes: dict[str, _BM25Index] = {}

        if path.is_dir():
            for pkl in sorted(path.glob("*.pkl")):
                # Convention: bm25_{law_id}.pkl or bm25_{so_hieu}.pkl
                law_id = pkl.stem.replace("bm25_", "").replace("_", "-")
                self._indexes[law_id] = _BM25Index(pkl)
        else:
            # Single file — infer law_id from filename
            law_id = path.stem.replace("bm25_", "").replace("_", "-")
            self._indexes[law_id] = _BM25Index(path)

    def search(
        self,
        query: str,
        top_k: int = 10,
        law_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Search across all loaded indexes.
        law_ids: filter by specific law_ids (None = search all)
        """
        target_indexes = self._indexes
        if law_ids:
            # Match by prefix or exact
            target_indexes = {
                k: v for k, v in self._indexes.items()
                if any(k.startswith(lid) or lid in k for lid in law_ids)
            }
            # Fallback: search all if no match
            if not target_indexes:
                target_indexes = self._indexes

        all_results: list[RetrievedChunk] = []
        for _law_id, idx in target_indexes.items():
            results = idx.search(query, top_k=top_k)
            all_results.extend(results)

        # Merge + sort by score
        all_results.sort(key=lambda c: c.score, reverse=True)
        return all_results[:top_k]

    def available_law_ids(self) -> list[str]:
        return list(self._indexes.keys())


# ── Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    index_path = sys.argv[1] if len(sys.argv) > 1 else "indexer/indexes"
    r = BM25Retriever(index_path)
    print(f"Loaded law_ids: {r.available_law_ids()}")
    results = r.search("người lao động đơn phương chấm dứt hợp đồng", top_k=3)
    for rc in results:
        print(f"  [{rc.score:.3f}] {rc.chunk_id} — {rc.ten_dieu[:50]}")
