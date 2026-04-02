"""
Qdrant Setup v2 — 11 payload indexes cho multi-law.
Chạy 1 lần để tạo collection + indexes.

Usage:
    python qdrant_setup.py [--recreate]
"""
from __future__ import annotations
import os, sys, argparse
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, SparseVectorParams, Modifier,
    PayloadSchemaType,
)

COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_vn_v2")

# ── Payload indexes (11 total) ────────────────────────────────
PAYLOAD_INDEXES = [
    # Integer indexes
    ("so_dieu",         PayloadSchemaType.INTEGER),
    ("khoan_so",        PayloadSchemaType.INTEGER),
    ("chuong_so",       PayloadSchemaType.INTEGER),
    ("thu_tu_uu_tien",  PayloadSchemaType.INTEGER),
    # Keyword indexes
    ("law_id",          PayloadSchemaType.KEYWORD),
    ("loai_van_ban",    PayloadSchemaType.KEYWORD),
    ("chunk_type",      PayloadSchemaType.KEYWORD),   # dieu | khoan
    ("van_ban_id",      PayloadSchemaType.KEYWORD),
    ("so_hieu",         PayloadSchemaType.KEYWORD),
    ("parent_dieu_id",  PayloadSchemaType.KEYWORD),
    # Text (for date range queries)
    ("ngay_hieu_luc",   PayloadSchemaType.KEYWORD),   # stored as YYYY-MM-DD string
]


def setup(recreate: bool = False):
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
        timeout=60,
    )

    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION in existing:
        if recreate:
            print(f"  Deleting collection '{COLLECTION}'...")
            client.delete_collection(COLLECTION)
        else:
            print(f"  Collection '{COLLECTION}' already exists. Use --recreate to reset.")
            _ensure_indexes(client)
            return

    print(f"  Creating collection '{COLLECTION}'...")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense_e5":  VectorParams(size=1024, distance=Distance.COSINE),
            "dense_bge": VectorParams(size=1024, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse_bge": SparseVectorParams(modifier=Modifier.IDF),
        },
    )

    _ensure_indexes(client)
    print(f"  ✅ Collection '{COLLECTION}' ready with {len(PAYLOAD_INDEXES)} payload indexes.")


def _ensure_indexes(client: QdrantClient):
    for field_name, schema_type in PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field_name,
                field_schema=schema_type,
            )
            print(f"    Index: {field_name} ({schema_type.value})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"    Index: {field_name} (already exists)")
            else:
                print(f"    ⚠️  Index {field_name} failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate collection")
    args = parser.parse_args()

    print(f"\n  Qdrant Setup v2 — Collection: {COLLECTION}")
    print(f"  URL: {os.getenv('QDRANT_URL', '(not set)')}")
    print()
    setup(recreate=args.recreate)
