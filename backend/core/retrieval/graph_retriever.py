"""
Citation Graph Retriever
-------------------------
Sau khi retriever trả về top-k chunks, expand thêm
các điều được tham chiếu tới (forward) và tham chiếu từ (backward).

Dùng trước reranker để tăng candidate pool cho multi-hop queries.

Ví dụ:
    Retriever: [Điều 48]
    Graph expand: Điều 48 → forward → [Điều 49]
    Pool mới: [Điều 48, Điều 49, ...]  → reranker chọn top-3
"""

import json
import pickle
from pathlib import Path
from dataclasses import dataclass

from backend.core.retrieval.base import RetrievedChunk, BM25Retriever


class CitationGraphRetriever:
    def __init__(self, graph_path: str, bm25_index_path: str):
        """
        Args:
            graph_path:      path tới citation_graph_*.json
            bm25_index_path: path tới bm25_*.pkl (để fetch chunk content)
        """
        with open(graph_path, encoding="utf-8") as f:
            graph = json.load(f)

        # Convert string keys → int (JSON serialize keys thành string)
        self.forward  = {int(k): v for k, v in graph["forward"].items()}
        self.backward = {int(k): v for k, v in graph["backward"].items()}
        self.dieu_meta = {int(k): v for k, v in graph["dieu_meta"].items()}

        # Load BM25 index để fetch chunk content theo so_dieu
        with open(bm25_index_path, "rb") as f:
            bm25_data = pickle.load(f)
        self._chunks_by_dieu = {c["so_dieu"]: c for c in bm25_data["chunks"]}

        print(f"[GraphRetriever] Loaded: {len(self.forward)} nodes with forward edges")

    def expand(
        self,
        chunks: list[RetrievedChunk],
        depth: int = 1,
        direction: str = "both",  # "forward" | "backward" | "both"
        max_expand: int = 5,
    ) -> list[RetrievedChunk]:
        """
        Expand retrieval results bằng citation graph.

        Args:
            chunks:     top-k từ retriever
            depth:      số bước hop (1 = chỉ neighbors trực tiếp)
            direction:  "forward" (A→B), "backward" (B←A), "both"
            max_expand: tối đa bao nhiêu chunk thêm vào

        Returns:
            list chunks gốc + chunks mới từ graph (deduped)
        """
        existing_dieu = {c.so_dieu for c in chunks}
        to_expand     = set(existing_dieu)
        new_dieu      = set()

        for _ in range(depth):
            next_expand = set()
            for dieu in to_expand:
                if direction in ("forward", "both"):
                    for target in self.forward.get(dieu, []):
                        if target not in existing_dieu:
                            new_dieu.add(target)
                            next_expand.add(target)

                if direction in ("backward", "both"):
                    for source in self.backward.get(dieu, []):
                        if source not in existing_dieu:
                            new_dieu.add(source)
                            next_expand.add(source)

            to_expand = next_expand
            if not to_expand:
                break

        # Giới hạn số lượng expand
        new_dieu = list(new_dieu)[:max_expand]

        # Fetch chunk content cho các điều mới
        new_chunks = []
        for dieu in new_dieu:
            chunk_data = self._chunks_by_dieu.get(dieu)
            if not chunk_data:
                continue
            new_chunks.append(RetrievedChunk(
                chunk_id    = chunk_data["id"],
                so_dieu     = chunk_data["so_dieu"],
                ten_dieu    = chunk_data["ten_dieu"],
                chuong_so   = chunk_data["chuong_so"],
                ten_chuong  = chunk_data["ten_chuong"],
                noi_dung    = chunk_data["noi_dung"],
                score       = 0.0,  # graph-expanded, không có retrieval score
                source      = "graph_expand",
            ))

        if new_chunks:
            print(f"[GraphRetriever] Expanded: +{len(new_chunks)} chunks "
                  f"(from {[c.so_dieu for c in chunks[:3]]}...)")

        return chunks + new_chunks

    def get_neighbors(self, so_dieu: int, direction: str = "both") -> list[int]:
        """Trả về danh sách điều neighbors."""
        result = []
        if direction in ("forward", "both"):
            result.extend(self.forward.get(so_dieu, []))
        if direction in ("backward", "both"):
            result.extend(self.backward.get(so_dieu, []))
        return list(set(result))


# ════════════════════════════════════════════════════════════
# Smoke test
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

    GRAPH_PATH = Path(__file__).parent.parent / "indexer/indexes/citation_graph_10.2012.QH13.json"
    BM25_PATH  = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"

    if not GRAPH_PATH.exists():
        print(f"Graph chưa có. Chạy: python graph_builder.py --input ../extractor/output/10.2012.QH13.json")
        sys.exit(1)

    gr = CitationGraphRetriever(str(GRAPH_PATH), str(BM25_PATH))

    # Test multi-hop cases
    print("\n── Test graph expansion ──")
    test_cases = [
        ("q020 Trợ cấp thôi việc",          [48]),   # Điều 48 → forward → Điều 49?
        ("q019 Chấm dứt trái pháp luật",    [43]),   # Điều 43 → forward → Điều 37, 38?
        ("q014 Trợ cấp mất việc",            [49]),   # Điều 49 ← backward ← Điều 48?
        ("q015 Sa thải lao động nữ mang thai", [39]), # Điều 39 liên quan điều nào?
    ]

    bm25 = BM25Retriever(str(BM25_PATH))

    for label, dieu_list in test_cases:
        # Tạo fake chunks từ danh sách điều
        fake_chunks = []
        for d in dieu_list:
            results = bm25.search(f"Điều {d}", top_k=50)
            match = next((r for r in results if r.so_dieu == d), None)
            if match:
                fake_chunks.append(match)

        if not fake_chunks:
            print(f"\n[{label}] Không tìm được chunk")
            continue

        expanded = gr.expand(fake_chunks, depth=1, direction="both", max_expand=5)
        orig_dieu = [c.so_dieu for c in fake_chunks]
        new_dieu  = [c.so_dieu for c in expanded if c.so_dieu not in orig_dieu]

        print(f"\n[{label}]")
        print(f"  Input:    Điều {orig_dieu}")
        print(f"  Expanded: +{new_dieu}")
        for c in expanded:
            tag = " [NEW]" if c.so_dieu not in orig_dieu else ""
            print(f"    Điều {c.so_dieu:3d}{tag} — {c.ten_dieu[:50]}")
