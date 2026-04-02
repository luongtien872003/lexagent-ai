"""
LexAgent Legal RAG — FastAPI Application v3
============================================
Start:
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import CORS_ORIGINS, EXTRACTOR_JSON, BM25_INDEX
from backend.services.pipeline_service    import PipelineService
from backend.services.conversation_service import ConversationService
from backend.services.document_service    import DocumentService
from backend.app.routers import health, documents, conversations


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 55)
    print("  LexAgent v3 — Multi-Law Legal RAG API")
    print("=" * 55)

    app.state.documents      = DocumentService(str(EXTRACTOR_JSON))
    app.state.conversations  = ConversationService()
    app.state.pipeline       = PipelineService()
    asyncio.create_task(app.state.pipeline.initialize())

    print("[API] Ready — models loading in background...")
    print("[API] GET /api/health để kiểm tra trạng thái")
    print("=" * 55)
    yield
    print("[API] Shutting down...")


app = FastAPI(
    title       = "LexAgent — Multi-Law Legal RAG API",
    description = "Vietnamese Labor Law AI Assistant (Multi-law v3)",
    version     = "3.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = [o for o in CORS_ORIGINS if o],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(conversations.router)


@app.get("/", tags=["root"])
async def root():
    return {
        "name":    "LexAgent v3",
        "docs":    "/docs",
        "health":  "/api/health",
        "version": "3.0.0",
    }
