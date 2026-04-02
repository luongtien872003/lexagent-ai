"""
Vector Indexer v2 — E5 + BGE-M3 → Qdrant
==========================================
Nâng cấp so với v1:
  - Index khoản-level chunks (type=khoan) thay vì chỉ dieu-level
  - Point ID = hash(chunk_id) thay vì so_dieu → không conflict multi-law
  - Payload đầy đủ v3: law_id, khoan_so, loai_van_ban, thu_tu_uu_tien, ngay_hieu_luc
  - Đọc QDRANT_COLLECTION từ .env (default: legal_vn_v2)
  - Batch size nhỏ (4) để không OOM trên CPU

Usage:
    python backend/core/indexing/vector_indexer.py --input data/extracted/lao-dong-2012/lao-dong-2012.json
    python backend/core/indexing/vector_indexer.py --input data/extracted/lao-dong-2012/lao-dong-2012.json --skip-bge
    python backend/core/indexing/vector_indexer.py --input data/extracted/lao-dong-2012/lao-dong-2012.json --skip-e5
"""

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path

from dotenv import load_dotenv
# Load .env từ project root (4 levels up từ backend/core/indexing/)
ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(ROOT / ".env")

# ── deps check ────────────────────────────────────────────────────
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, SparseVector
except ImportError:
    raise SystemExit("Thiếu qdrant-client. Chạy: pip install qdrant-client")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise SystemExit("Thiếu sentence-transformers. Chạy: pip install sentence-transformers")

# ── config ────────────────────────────────────────────────────────
QDRANT_URL        = os.getenv("QDRANT_URL")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_vn_v2")
E5_MODEL          = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
BGE_MODEL         = "BAAI/bge-m3"
BATCH_SIZE        = 4
RETRY_TIMES       = 3
RETRY_DELAY       = 2


# ── Point ID ──────────────────────────────────────────────────────
def make_point_id(chunk_id: str, offset: int = 0) -> int:
    """
    Hash chunk_id → stable int ID.
    offset: 0 cho E5, 10_000_000 cho BGE (tránh conflict).
    Dùng hash thay vì so_dieu để support multi-law (2 luật có thể có cùng Điều 37).
    """
    h = int(hashlib.md5(chunk_id.encode()).hexdigest(), 16) % (10 ** 9)
    return h + offset


# ── Payload v3 ────────────────────────────────────────────────────
def _make_payload(chunk: dict) -> dict:
    """Build Qdrant payload với đầy đủ fields v3."""
    return {
        # Core fields
        "chunk_id"      : chunk.get("id", ""),
        "van_ban_id"    : chunk.get("van_ban_id", ""),
        "so_hieu"       : chunk.get("so_hieu", ""),
        "so_dieu"       : chunk.get("so_dieu", 0),
        "ten_dieu"      : chunk.get("ten_dieu", ""),
        "chuong_so"     : chunk.get("chuong_so", 0),
        "ten_chuong"    : chunk.get("ten_chuong", ""),
        "noi_dung"      : chunk.get("noi_dung", ""),
        "chunk_type"    : chunk.get("type", "dieu"),   # dieu | khoan
        # v3 multi-law fields
        "law_id"        : chunk.get("law_id", "unknown"),
        "khoan_so"      : chunk.get("khoan_so", 0),
        "loai_van_ban"  : chunk.get("loai_van_ban", "luat"),
        "thu_tu_uu_tien": chunk.get("thu_tu_uu_tien", 1),
        "ngay_hieu_luc" : chunk.get("ngay_hieu_luc", ""),
        "context_header": chunk.get("context_header", ""),
        "parent_dieu_id": chunk.get("parent_dieu_id", ""),
        # Extra
        "entities"      : chunk.get("entities", []),
    }


# ── Qdrant client ─────────────────────────────────────────────────
def get_client() -> QdrantClient:
    if not QDRANT_URL or not QDRANT_API_KEY:
        raise ValueError("Thiếu QDRANT_URL hoặc QDRANT_API_KEY trong .env")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)
    try:
        info = client.get_collection(QDRANT_COLLECTION)
        print(f"[Qdrant] Connected. Collection '{QDRANT_COLLECTION}' — status={info.status}")
        return client
    except Exception as e:
        raise ConnectionError(
            f"Không kết nối được Qdrant hoặc collection chưa tồn tại: {e}\n"
            f"Chạy 'python scripts/setup_qdrant.py' trước."
        )


def upsert_with_retry(client: QdrantClient, points: list, label: str):
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            client.upsert(collection_name=QDRANT_COLLECTION, points=points)
            return
        except Exception as e:
            print(f"  [WARN] {label} upsert attempt {attempt}/{RETRY_TIMES}: {e}")
            if attempt < RETRY_TIMES:
                time.sleep(RETRY_DELAY * attempt)
    print(f"  [ERROR] {label} upsert failed after {RETRY_TIMES} attempts")


# ── E5 Indexer ────────────────────────────────────────────────────
def index_e5(chunks: list, client: QdrantClient):
    print(f"\n[E5] Loading {E5_MODEL}...")
    model = SentenceTransformer(E5_MODEL)
    print(f"[E5] Embedding {len(chunks)} chunks (batch={BATCH_SIZE})...")

    all_embeddings = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]
        texts = [c.get("text_for_embedding", c.get("noi_dung", "")) for c in batch]
        embs  = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.extend(embs)
        if (i // BATCH_SIZE) % 10 == 0:
            print(f"  E5: {i+len(batch)}/{len(chunks)}")

    points = []
    for chunk, emb in zip(chunks, all_embeddings):
        chunk_id = chunk.get("id", f"chunk_{chunk.get('so_dieu',0)}")
        points.append(PointStruct(
            id      = make_point_id(chunk_id, offset=0),
            vector  = {"dense_e5": emb.tolist()},
            payload = _make_payload(chunk),
        ))

    # Upsert in batches of 50
    for i in range(0, len(points), 50):
        batch = points[i: i + 50]
        upsert_with_retry(client, batch, f"E5 batch {i//50+1}")
        print(f"  E5 upserted: {i+len(batch)}/{len(points)}")

    print(f"[E5] Done — {len(points)} points")


# ── BGE-M3 Indexer ────────────────────────────────────────────────
def index_bge(chunks: list, client: QdrantClient):
    print(f"\n[BGE] Loading {BGE_MODEL}...")
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError:
        raise SystemExit("Thiếu FlagEmbedding. Chạy: pip install FlagEmbedding transformers==4.44.2")

    model = BGEM3FlagModel(BGE_MODEL, use_fp16=False)
    print(f"[BGE] Encoding {len(chunks)} chunks (batch={BATCH_SIZE})...")

    points = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch_chunks = chunks[i: i + BATCH_SIZE]
        texts = [c.get("text_for_embedding", c.get("noi_dung", "")) for c in batch_chunks]

        out = model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
            batch_size=BATCH_SIZE,
        )
        dense_vecs    = out["dense_vecs"]
        lexical_weights = out["lexical_weights"]

        for j, chunk in enumerate(batch_chunks):
            chunk_id = chunk.get("id", f"chunk_{chunk.get('so_dieu',0)}")
            dense    = dense_vecs[j].tolist()
            sparse_w = lexical_weights[j]

            # Sparse vector
            indices = [int(k) for k in sparse_w.keys()]
            values  = [float(v) for v in sparse_w.values()]

            points.append(PointStruct(
                id     = make_point_id(chunk_id, offset=10_000_000),
                vector = {
                    "dense_bge":  dense,
                    "sparse_bge": SparseVector(indices=indices, values=values),
                },
                payload = _make_payload(chunk),
            ))

        if (i // BATCH_SIZE) % 10 == 0:
            print(f"  BGE: {i+len(batch_chunks)}/{len(chunks)}")

    # Upsert
    for i in range(0, len(points), 50):
        batch = points[i: i + 50]
        upsert_with_retry(client, batch, f"BGE batch {i//50+1}")
        print(f"  BGE upserted: {i+len(batch)}/{len(points)}")

    print(f"[BGE] Done — {len(points)} points")


# ── Load chunks ───────────────────────────────────────────────────
def load_chunks(json_path: Path) -> list:
    """Load chunks từ extractor JSON. Prefer khoản-level, fallback dieu-level."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    all_chunks   = data.get("chunks", [])
    khoan_chunks = [c for c in all_chunks if c.get("type") == "khoan"]
    dieu_chunks  = [c for c in all_chunks if c.get("type") == "dieu"]

    if khoan_chunks:
        # Index cả khoản (granular) lẫn dieu (fallback retrieval)
        result = khoan_chunks + dieu_chunks
        # Lọc bỏ chunks rỗng
        result = [c for c in result if len(c.get("noi_dung", "")) >= 30]
        print(f"[Loader] {len(khoan_chunks)} khoản + {len(dieu_chunks)} dieu = {len(result)} total chunks")
    else:
        result = dieu_chunks
        print(f"[Loader] {len(dieu_chunks)} dieu-level chunks (no khoản found)")

    return result


# ── Smoke test ────────────────────────────────────────────────────
def smoke_test(client: QdrantClient):
    print(f"\n[Smoke test] Collection '{QDRANT_COLLECTION}':")
    count = client.count(QDRANT_COLLECTION).count
    print(f"  Total points: {count}")

    # Sample query
    try:
        result = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=3,
            with_payload=True,
            with_vectors=False,
        )
        for point in result[0]:
            p = point.payload
            print(f"  Sample: [{p.get('law_id')}] Điều {p.get('so_dieu')} Khoản {p.get('khoan_so')} — {p.get('ten_dieu','')[:40]}")
    except Exception as e:
        print(f"  Scroll error: {e}")


# ── Main ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vector Indexer v2")
    parser.add_argument("--input",    required=True, help="Path to extractor JSON")
    parser.add_argument("--skip-e5",  action="store_true", help="Skip E5 indexing")
    parser.add_argument("--skip-bge", action="store_true", help="Skip BGE indexing")
    args = parser.parse_args()

    json_path = Path(args.input)
    if not json_path.exists():
        raise SystemExit(f"File not found: {json_path}")

    print(f"\n{'='*55}")
    print(f"  Vector Indexer v2")
    print(f"  Input:      {json_path}")
    print(f"  Collection: {QDRANT_COLLECTION}")
    print(f"  E5:  {'skip' if args.skip_e5  else 'YES'}")
    print(f"  BGE: {'skip' if args.skip_bge else 'YES'}")
    print(f"{'='*55}\n")

    client = get_client()
    chunks = load_chunks(json_path)

    if not chunks:
        raise SystemExit("No chunks found in input file.")

    t0 = time.time()

    if not args.skip_e5:
        index_e5(chunks, client)

    if not args.skip_bge:
        index_bge(chunks, client)

    smoke_test(client)
    print(f"\n✅ Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()