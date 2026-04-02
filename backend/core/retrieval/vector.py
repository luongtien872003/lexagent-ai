"""
Vector Retriever — query Qdrant cho E5 và BGE-M3.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector
from sentence_transformers import SentenceTransformer
import torch

from backend.core.retrieval.base import RetrievedChunk

QDRANT_URL        = os.getenv("QDRANT_URL")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_vn")


class VectorRetriever:
    """
    Dùng cho cả E5 (dense_e5) và BGE dense (dense_bge).
    vector_name: "dense_e5" hoặc "dense_bge"
    embed_prefix: "query: " cho E5, "" cho BGE
    """
    def __init__(self, model_name: str, vector_name: str, embed_prefix: str = ""):
        print(f"[Vector:{vector_name}] Loading {model_name}...")
        self.model        = SentenceTransformer(model_name)
        self.vector_name  = vector_name
        self.embed_prefix = embed_prefix
        self.client       = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
        self.collection   = QDRANT_COLLECTION
        print(f"[Vector:{vector_name}] Ready")

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        text = self.embed_prefix + query
        with torch.no_grad():
            emb = self.model.encode(text, normalize_embeddings=True).tolist()

        results = self.client.query_points(
            collection_name=self.collection,
            query=emb,
            using=self.vector_name,
            limit=top_k,
            with_payload=True,
        ).points
        return [_hit_to_chunk(h, self.vector_name) for h in results]


class BGESparseRetriever:
    """
    BGE-M3 sparse vector retrieval qua Qdrant sparse_bge.
    """
    def __init__(self):
        print("[BGE-Sparse] Loading BAAI/bge-m3...")
        try:
            from FlagEmbedding import BGEM3FlagModel
            self.model     = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
            self._use_flag = True
        except Exception as e:
            raise RuntimeError(f"FlagEmbedding load failed: {e}")
        self.client     = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
        self.collection = QDRANT_COLLECTION
        print("[BGE-Sparse] Ready")

    def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        out     = self.model.encode([query], return_dense=False, return_sparse=True, return_colbert_vecs=False)
        sw      = out["lexical_weights"][0]
        indices = [int(k) for k in sw.keys()]
        values  = [float(v) for v in sw.values()]

        results = self.client.query_points(
            collection_name=self.collection,
            query=SparseVector(indices=indices, values=values),
            using="sparse_bge",
            limit=top_k,
            with_payload=True,
        ).points
        return [_hit_to_chunk(h, "sparse_bge") for h in results]


def _hit_to_chunk(hit, source: str) -> RetrievedChunk:
    p = hit.payload
    return RetrievedChunk(
        chunk_id   = p["chunk_id"],
        so_dieu    = p["so_dieu"],
        ten_dieu   = p["ten_dieu"],
        chuong_so  = p["chuong_so"],
        ten_chuong = p["ten_chuong"],
        noi_dung   = p["noi_dung"],
        score      = float(hit.score),
        source     = source,
    )
