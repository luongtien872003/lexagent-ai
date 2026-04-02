"""
LexAgent — Central Configuration (production layout)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR    = Path(__file__).parent.parent.parent   # project root
BACKEND_DIR = Path(__file__).parent.parent          # backend/
load_dotenv(ROOT_DIR / ".env")

# ── Qdrant ────────────────────────────────────────────────
QDRANT_URL        = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_vn_v2")

# ── Embeddings / Reranker ─────────────────────────────────
EMBED_MODEL    = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# ── OpenAI ────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = "gpt-4o-mini"   # cheap, fast for decompose/verify

MODEL_TIERS: dict[str, dict] = {
    "fast": {
        "model_id":    "gpt-4o-mini",
        "name":        "Nhanh",
        "description": "Câu hỏi đơn giản, tra cứu nhanh",
        "cost_vnd":    50,
        "max_tokens":  1800,
    },
    "balanced": {
        "model_id":    "gpt-4.1-mini",
        "name":        "Cân bằng",
        "description": "Phân tích tốt hơn, giá hợp lý",
        "cost_vnd":    130,
        "max_tokens":  2500,
    },
    "precise": {
        "model_id":    "gpt-4o",
        "name":        "Chính xác",
        "description": "Phân tích pháp lý phức tạp",
        "cost_vnd":    700,
        "max_tokens":  3500,
    },
}
DEFAULT_TIER = "fast"

def get_model(tier: str) -> str:
    return MODEL_TIERS.get(tier, MODEL_TIERS[DEFAULT_TIER])["model_id"]

def get_max_tokens(tier: str) -> int:
    return MODEL_TIERS.get(tier, MODEL_TIERS[DEFAULT_TIER])["max_tokens"]

# ── Data paths ────────────────────────────────────────────
DATA_DIR       = ROOT_DIR / "data"
INDEXES_DIR    = DATA_DIR / "indexes"
EXTRACTED_DIR  = DATA_DIR / "extracted"
RAW_DIR        = DATA_DIR / "raw"

# Legacy single-law paths (lao-dong-2012)
EXTRACTOR_JSON = ROOT_DIR / "extractor" / "output" / "10.2012.QH13.json"
BM25_INDEX_DIR = INDEXES_DIR                      # Multi-law: scan all .pkl
BM25_INDEX     = INDEXES_DIR / "bm25_lao-dong-2012.pkl"
KG_PATH        = INDEXES_DIR / "kg_10.2012.QH13.json"
CITATION_PATH  = INDEXES_DIR / "citation_graph_10.2012.QH13.json"

# ── Pipeline ──────────────────────────────────────────────
HYBRID_ALPHA        = 0.5
MAX_AGENTIC_ROUNDS  = 3

# ── API ───────────────────────────────────────────────────
API_HOST     = "0.0.0.0"
API_PORT     = 8000
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    os.getenv("FRONTEND_URL", ""),
]
