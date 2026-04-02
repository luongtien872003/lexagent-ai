"""
Health check router.
"""
from fastapi import APIRouter, Request
from backend.app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check(request: Request):
    pipeline = request.app.state.pipeline
    doc_svc = request.app.state.documents

    qdrant_ok = False
    try:
        if pipeline.ready:
            c = pipeline._components
            if c and c.get("e5"):
                qdrant_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ready" if pipeline.ready else "loading",
        models_loaded=pipeline.ready,
        document_count=doc_svc.dieu_count if doc_svc else 0,
        qdrant_connected=qdrant_ok,
        uptime_seconds=round(pipeline.uptime, 1),
    )
