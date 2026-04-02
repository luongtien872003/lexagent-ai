"""
Knowledge Graph Retriever v2
------------------------------
Improvements vs v1:
  1. Hybrid: Citation Graph + Knowledge Graph cùng lúc
  2. Confidence scoring — KG triple có score, Citation Graph có score riêng
  3. Better entity matching — longest match first + partial match có weight thấp hơn
  4. Debug mode — in rõ lý do tại sao mỗi điều được thêm vào

Pipeline:
  query
    ↓
  extract_entities()          → ["người lao động", "đình công", ...]
    ↓
  KG entity_index lookup      → Điều 5, 209, 210 (từ KG)
  Citation Graph forward/back → Điều 38, 39 (từ Citation)
    ↓
  score & merge               → ranked list
    ↓
  fetch chunks & return       → extra RetrievedChunk list
"""

import json
import pickle
from pathlib import Path
from dataclasses import dataclass

from backend.core.retrieval.base import RetrievedChunk

STOPWORDS = {
    "có", "là", "được", "không", "theo", "của", "và", "hoặc",
    "trong", "tại", "về", "cho", "với", "từ", "đến", "các",
    "những", "này", "đó", "khi", "nếu", "thì", "mà", "để",
    "bộ", "luật", "điều", "khoản", "điểm", "mục", "chương",
    "người", "có thể", "phải", "nên",
}

# Canonical map — query term → KG entity chuẩn
ENTITY_CANONICAL = {
    # Chủ thể
    "người lao động":            "người lao động",
    "nlđ":                       "người lao động",
    "công nhân":                 "người lao động",
    "nhân viên":                 "người lao động",
    "người sử dụng lao động":    "người sử dụng lao động",
    "nsdlđ":                     "người sử dụng lao động",
    "chủ doanh nghiệp":          "người sử dụng lao động",
    "sếp":                       "người sử dụng lao động",
    "công ty":                   "người sử dụng lao động",
    "doanh nghiệp":              "người sử dụng lao động",
    "tổ chức công đoàn":         "tổ chức công đoàn",
    "công đoàn":                 "tổ chức công đoàn",
    "người học nghề":            "người học nghề",
    "lao động nữ":               "lao động nữ",
    "lao động chưa thành niên":  "lao động chưa thành niên",
    "người khuyết tật":          "người khuyết tật",

    # Hành vi
    "sa thải":                   "đơn phương chấm dứt hợp đồng lao động",
    "đuổi việc":                 "đơn phương chấm dứt hợp đồng lao động",
    "cho thôi việc":             "đơn phương chấm dứt hợp đồng lao động",
    "nghỉ việc":                 "chấm dứt hợp đồng lao động",
    "thôi việc":                 "chấm dứt hợp đồng lao động",
    "tự ý nghỉ việc":            "đơn phương chấm dứt hợp đồng lao động",
    "đình công":                 "đình công",
    "bãi công":                  "đình công",
    "ngừng việc tập thể":        "đình công",
    "thử việc":                  "thời gian thử việc",
    "kỷ luật":                   "kỷ luật lao động",
    "làm thêm giờ":              "giờ làm thêm",
    "tăng ca":                   "giờ làm thêm",
    "đóng cửa tạm thời":         "đóng cửa nơi làm việc",

    # Quyền lợi
    "trợ cấp thôi việc":         "trợ cấp thôi việc",
    "tiền thôi việc":            "trợ cấp thôi việc",
    "trợ cấp mất việc":          "trợ cấp mất việc làm",
    "tiền lương":                "tiền lương",
    "lương":                     "tiền lương",
    "nghỉ phép":                 "nghỉ hằng năm",
    "phép năm":                  "nghỉ hằng năm",
    "thai sản":                  "nghỉ thai sản",
    "mang thai":                 "lao động nữ mang thai",
    "bảo hiểm xã hội":           "bảo hiểm xã hội",
    "bhxh":                      "bảo hiểm xã hội",

    # Điều kiện
    "tuổi lao động":             "tuổi lao động",
    "độ tuổi":                   "tuổi lao động",
    "15 tuổi":                   "tuổi lao động",
    "hợp đồng lao động":         "hợp đồng lao động",
    "hđlđ":                      "hợp đồng lao động",

    # Hậu quả
    "bồi thường":                "bồi thường",
    "bồi hoàn":                  "bồi thường",
    "bị phạt":                   "xử phạt vi phạm",
}


@dataclass
class ExpandedChunk:
    """Wrapper chunk với thêm source info."""
    chunk:      RetrievedChunk
    expand_score: float     # confidence của expansion
    expand_source: str      # "kg" | "citation" | "kg+citation"
    matched_entities: list[str]


class KGRetriever:
    def __init__(
        self,
        kg_path:        str,
        bm25_index_path: str,
        citation_graph_path: str | None = None,
    ):
        # Load KG
        with open(kg_path, encoding="utf-8") as f:
            kg = json.load(f)
        self.triples      = kg["triples"]
        self.entity_index = {k.lower(): v for k, v in kg["entity_index"].items()}

        # Load Citation Graph (optional)
        self.citation_forward:  dict[int, list[int]] = {}
        self.citation_backward: dict[int, list[int]] = {}
        if citation_graph_path and Path(citation_graph_path).exists():
            with open(citation_graph_path, encoding="utf-8") as f:
                cg = json.load(f)
            self.citation_forward  = {int(k): v for k, v in cg["forward"].items()}
            self.citation_backward = {int(k): v for k, v in cg["backward"].items()}
            print(f"[KGRetriever] Citation graph: {len(self.citation_forward)} nodes")

        # Load BM25 để fetch chunk content
        with open(bm25_index_path, "rb") as f:
            bm25_data = pickle.load(f)
        self._chunks_by_dieu = {c.get("so_dieu", c.get("id", i)): c for i, c in enumerate(bm25_data["chunks"])}

        print(f"[KGRetriever] KG: {len(self.triples)} triples, "
              f"{len(self.entity_index)} entities")

    def extract_entities(self, query: str) -> list[str]:
        """
        Extract entities từ query.
        Ưu tiên longest match để tránh partial false positive.
        """
        q_lower = query.lower()
        found   = {}  # entity → score

        # 1. Canonical map — sort by length DESC
        for term in sorted(ENTITY_CANONICAL, key=len, reverse=True):
            if term in q_lower:
                canonical = ENTITY_CANONICAL[term]
                if canonical not in found:
                    found[canonical] = 1.0  # exact canonical match

        # 2. Direct entity_index lookup
        for ent in sorted(self.entity_index, key=len, reverse=True):
            if len(ent) < 4 or ent in STOPWORDS:
                continue
            if ent in q_lower and ent not in found:
                found[ent] = 0.8  # direct match

        # Sort by score desc
        return [e for e, _ in sorted(found.items(), key=lambda x: x[1], reverse=True)]

    def _kg_lookup(
        self,
        entities:        list[str],
        exclude_dieu:    set[int],
        max_results:     int,
        hub_threshold:   int   = 15,
        score_threshold: float = 1.5,
    ) -> dict[int, float]:
        """
        Lookup điều từ KG entity_index.
        Fix 1: hub_threshold — skip entity map đến > N điều (quá chung chung)
        Fix 2: score_threshold — chỉ expand điều có signal đủ mạnh
        """
        dieu_score: dict[int, float] = {}

        for entity in entities:
            ent_lower = entity.lower()
            dieu_list = self.entity_index.get(ent_lower, [])

            # Fix 1: skip hub nodes
            if len(dieu_list) > hub_threshold:
                continue

            for dieu in dieu_list:
                if dieu not in exclude_dieu:
                    dieu_score[dieu] = dieu_score.get(dieu, 0) + 1.0

            for idx_ent, idx_dieu_list in self.entity_index.items():
                if idx_ent == ent_lower:
                    continue
                if len(idx_dieu_list) > hub_threshold:
                    continue
                if (ent_lower in idx_ent and len(ent_lower) >= 5) or \
                   (idx_ent in ent_lower and len(idx_ent) >= 5):
                    for dieu in idx_dieu_list:
                        if dieu not in exclude_dieu:
                            dieu_score[dieu] = dieu_score.get(dieu, 0) + 0.4

        # Fix 2: score threshold
        filtered = {d: s for d, s in dieu_score.items() if s >= score_threshold}
        sorted_dieu = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_dieu[:max_results])

    def _citation_lookup(
        self,
        existing_dieu: set[int],
        exclude_dieu:  set[int],
        max_results:   int,
    ) -> dict[int, float]:
        """Lookup điều từ Citation Graph."""
        dieu_score: dict[int, float] = {}
        for dieu in existing_dieu:
            for target in self.citation_forward.get(dieu, []):
                if target not in exclude_dieu:
                    dieu_score[target] = dieu_score.get(target, 0) + 0.8
            for source in self.citation_backward.get(dieu, []):
                if source not in exclude_dieu:
                    dieu_score[source] = dieu_score.get(source, 0) + 0.6
        sorted_dieu = sorted(dieu_score.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_dieu[:max_results])

    def expand(
        self,
        query:       str,
        chunks:      list[RetrievedChunk],
        max_expand:  int = 5,
        debug:       bool = False,
    ) -> list[RetrievedChunk]:
        """
        Expand retrieval results bằng KG + Citation Graph.

        Args:
            query:      câu hỏi gốc
            chunks:     top-k từ retriever
            max_expand: tối đa thêm bao nhiêu chunk
            debug:      in chi tiết lý do expand

        Returns:
            list chunks mới (chưa có trong chunks gốc), sorted by score
        """
        existing_dieu = {c.so_dieu for c in chunks}

        # Extract entities
        entities = self.extract_entities(query)
        if not entities and not self.citation_forward:
            return []

        if debug:
            print(f"[KGRetriever] Entities: {entities[:5]}")

        # KG lookup
        kg_scores = self._kg_lookup(entities, existing_dieu, max_expand * 2)

        # Citation lookup
        cite_scores = self._citation_lookup(existing_dieu, existing_dieu, max_expand)

        # Merge scores — điều xuất hiện ở cả 2 source được boost
        merged: dict[int, dict] = {}
        for dieu, score in kg_scores.items():
            merged[dieu] = {"score": score, "source": "kg"}
        for dieu, score in cite_scores.items():
            if dieu in merged:
                merged[dieu]["score"] += score
                merged[dieu]["source"] = "kg+citation"
            else:
                merged[dieu] = {"score": score, "source": "citation"}

        # Sort và lấy top max_expand
        sorted_merged = sorted(merged.items(), key=lambda x: x[1]["score"], reverse=True)
        top_new = sorted_merged[:max_expand]

        if debug:
            for dieu, info in top_new:
                meta = self._chunks_by_dieu.get(dieu, {})
                print(f"  → Điều {dieu:3d} (score={info['score']:.1f}, "
                      f"src={info['source']}) — {meta.get('ten_dieu','?')[:40]}")

        # Fetch chunks
        new_chunks = []
        for dieu, info in top_new:
            chunk_data = self._chunks_by_dieu.get(dieu)
            if not chunk_data:
                continue
            new_chunks.append(RetrievedChunk(
                chunk_id   = chunk_data["id"],
                so_dieu    = chunk_data["so_dieu"],
                ten_dieu   = chunk_data["ten_dieu"],
                chuong_so  = chunk_data["chuong_so"],
                ten_chuong = chunk_data["ten_chuong"],
                noi_dung   = chunk_data["noi_dung"],
                score      = info["score"],
                source     = f"expand_{info['source']}",
            ))

        if new_chunks:
            print(f"[KGRetriever] +{len(new_chunks)} chunks: "
                  f"{[c.so_dieu for c in new_chunks]}")

        return new_chunks


# ════════════════════════════════════════════════════════════
# Smoke test
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))

    KG_PATH   = Path(__file__).parent.parent / "indexer/indexes/kg_10.2012.QH13.json"
    CITE_PATH = Path(__file__).parent.parent / "indexer/indexes/citation_graph_10.2012.QH13.json"
    BM25_PATH = Path(__file__).parent.parent / "indexer/indexes/bm25_10.2012.QH13.pkl"

    # Thử với dryrun kg nếu full kg chưa có
    if not KG_PATH.exists():
        dryrun = Path(__file__).parent.parent / "indexer/indexes/kg_10.2012.QH13_dryrun.json"
        if dryrun.exists():
            KG_PATH = dryrun
            print("[Test] Dùng dry-run KG")
        else:
            print("KG chưa có. Chạy: python kg_builder.py --input ... --dry-run")
            sys.exit(1)

    from backend.core.retrieval.bm25 import BM25Retriever
    kg   = KGRetriever(str(KG_PATH), str(BM25_PATH),
                       citation_graph_path=str(CITE_PATH) if CITE_PATH.exists() else None)
    bm25 = BM25Retriever(str(BM25_PATH))

    test_cases = [
        ("q020", "Trợ cấp thôi việc được tính như thế nào và ai được nhận?",        [48, 49]),
        ("q015", "Công ty muốn sa thải nhân viên đang mang thai có hợp pháp không?", [39]),
        ("q004", "Người lao động có quyền đình công không?",                          [5]),
        ("q019", "Người lao động đơn phương chấm dứt hợp đồng trái pháp luật bồi thường gì?", [43]),
        ("q016", "Tôi bị sếp ép làm thêm giờ không trả lương tôi có quyền nghỉ việc không?", [37]),
    ]

    print("\n── KG Retriever v2 Smoke Test ──")
    print("=" * 68)

    for qid, query, gt in test_cases:
        top5 = bm25.search(query, top_k=5)
        top5_dieu = [c.so_dieu for c in top5]

        new_chunks = kg.expand(query, top5, max_expand=5, debug=True)
        new_dieu   = [c.so_dieu for c in new_chunks]

        all_dieu = set(top5_dieu) | set(new_dieu)
        gt_hit   = all(g in all_dieu for g in gt)

        print(f"\n[{qid}] {query[:55]}...")
        print(f"  BM25 top5 : {top5_dieu}")
        print(f"  KG expand : {new_dieu}")
        print(f"  GT {gt}   : {'✓ covered' if gt_hit else '✗ missing'}")
        print()