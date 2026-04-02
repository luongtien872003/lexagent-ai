"""
Citation Graph Builder
-----------------------
Đọc references có sẵn trong JSON extractor output
→ build citation graph → save graph.json

Chạy:
    python graph_builder.py --input ../extractor/output/10.2012.QH13.json

Output: indexer/indexes/citation_graph_10.2012.QH13.json
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

INDEXES_DIR = Path(__file__).parent / "indexes"
INDEXES_DIR.mkdir(exist_ok=True)


def build_citation_graph(json_path: str) -> dict:
    json_path = Path(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    doc    = data["document"]
    chunks = [c for c in data["chunks"] if c["type"] == "dieu"]

    print(f"[Graph] Van ban: {doc['ten_van_ban']} — {len(chunks)} dieu")

    # Build forward edges: dieu A → [dieu B, C, ...]
    forward: dict[int, list[int]] = defaultdict(list)
    # Build backward edges: dieu B ← [dieu A, ...] (ai tham chiếu tới B)
    backward: dict[int, list[int]] = defaultdict(list)
    # Metadata từng điều
    dieu_meta: dict[int, dict] = {}

    for chunk in chunks:
        so_dieu = chunk["so_dieu"]
        dieu_meta[so_dieu] = {
            "so_dieu":    so_dieu,
            "ten_dieu":   chunk["ten_dieu"],
            "chuong_so":  chunk["chuong_so"],
            "ten_chuong": chunk["ten_chuong"],
        }

        refs = chunk.get("references", [])
        for ref in refs:
            target = ref.get("target_dieu")
            # Bỏ self-reference và target không hợp lệ
            if not target or target == so_dieu:
                continue
            if target not in [r for r in forward[so_dieu]]:
                forward[so_dieu].append(target)
                backward[target].append(so_dieu)

    # Convert defaultdict → plain dict
    forward  = dict(forward)
    backward = dict(backward)

    # Stats
    total_edges  = sum(len(v) for v in forward.values())
    nodes_w_refs = len(forward)
    print(f"[Graph] Nodes: {len(chunks)}")
    print(f"[Graph] Edges: {total_edges} (forward citations)")
    print(f"[Graph] Điều có tham chiếu: {nodes_w_refs}/{len(chunks)}")

    graph = {
        "van_ban_id": doc["id"],
        "so_hieu":    doc["so_hieu"],
        "forward":    forward,   # A → [B, C]
        "backward":   backward,  # B ← [A]
        "dieu_meta":  dieu_meta,
    }

    out_path = INDEXES_DIR / f"citation_graph_{doc['id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"[Graph] Saved → {out_path}")

    # Smoke test — in top 5 điều được tham chiếu nhiều nhất
    most_cited = sorted(backward.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    print("\n[Graph] Top 5 điều được tham chiếu nhiều nhất:")
    for dieu, sources in most_cited:
        meta = dieu_meta.get(dieu, {})
        print(f"  Điều {dieu:3d} ({len(sources):2d} refs) — {meta.get('ten_dieu','?')[:50]}")

    return graph


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    build_citation_graph(args.input)
