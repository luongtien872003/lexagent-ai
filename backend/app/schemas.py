"""
Pydantic request/response models cho API.

THAY ĐỔI SO VỚI ORIGINAL:
- Thêm StructuredSection, StructuredAnswer — mirror JSON format từ LLM
- MessageResponse có thêm optional `structured` field
- Thêm SSESectionsEvent — sections được emit TRƯỚC khi token streaming bắt đầu
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ── Conversations ─────────────────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    title: str = ""
    mode:  str = Field(default="standard", pattern="^(standard|agentic)$")


class SendMessageRequest(BaseModel):
    content:    str = Field(..., min_length=1, max_length=2000)
    stream:     bool = True
    mode:       str  = Field(default="agentic", pattern="^(standard|agentic)$")
    model_tier: str  = Field(default="fast", pattern="^(fast|balanced|precise)$")


class Citation(BaseModel):
    index:            int
    so_dieu:          int
    ten_dieu:         str
    chuong_so:        int
    ten_chuong:       str
    van_ban:          str   = "BLLĐ 10/2012/QH13"
    relevance_score:  float = 0.0
    noi_dung_snippet: str   = ""
    so_khoan:         int   = 0    # 0 = toàn điều; >0 = khoản cụ thể từ LLM


class MessageMetadata(BaseModel):
    intent:          str       = ""
    pipeline:        str       = "standard"
    elapsed_sec:     float     = 0.0
    retrieval_top5:  list[int] = []
    reranked_top3:   list[int] = []
    sub_queries:     list[str] = []     # agentic mode: các sub-queries đã tách
    agentic_rounds:  int       = 0      # agentic mode: số vòng verify


# ── Structured answer ─────────────────────────────────────────────────────────

class StructuredSection(BaseModel):
    title:            str
    bullets:          list[str] = []
    citation_ids:     list[int] = Field(default=[], description="so_dieu list")
    citation_khoans:  dict      = Field(default={}, description="{so_dieu: so_khoan} từ LLM")


class StructuredAnswer(BaseModel):
    summary:  str
    sections: list[StructuredSection] = []


class MessageResponse(BaseModel):
    id:         str
    role:       str
    content:    str                              # raw text (backward compat)
    structured: Optional[StructuredAnswer] = None  # parsed structured answer
    citations:  list[Citation]             = []
    metadata:   MessageMetadata            = MessageMetadata()
    created_at: str                        = ""


class ConversationResponse(BaseModel):
    id:         str
    title:      str
    mode:       str
    created_at: str
    messages:   list[MessageResponse] = []


# ── Documents ─────────────────────────────────────────────────────────────────

class KhoanResponse(BaseModel):
    so_khoan: int
    noi_dung: str
    diem:     list[dict] = []


class DieuResponse(BaseModel):
    van_ban_id:   str
    van_ban_name: str
    so_dieu:      int
    ten_dieu:     str
    chuong_so:    int
    ten_chuong:   str
    noi_dung:     str
    khoan:        list[KhoanResponse] = []
    references:   list[dict]          = []
    entities:     list[str]           = []


class DocumentInfoResponse(BaseModel):
    id:               str
    ten_van_ban:      str
    so_hieu:          str
    co_quan_ban_hanh: str
    ngay_ban_hanh:    str
    tong_so_dieu:     int
    tong_so_chuong:   int


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:           str
    models_loaded:    bool
    document_count:   int
    qdrant_connected: bool
    uptime_seconds:   float


# ── SSE Events ────────────────────────────────────────────────────────────────

class SSEStatusEvent(BaseModel):
    """Pipeline stage progress."""
    type:     str  = "status"
    step:     str             # classifying | retrieving | reranking | generating
    detail:   str             # text thực từ backend
    meta:     str  = ""       # expandable detail (sub-queries, articles found, verdict)
    new_step: bool = True     # True = append new step row; False = update current row detail


class SSETokenEvent(BaseModel):
    """Phrase chunk được stream từ LLM summary."""
    type:    str = "token"
    content: str


class SSESectionsEvent(BaseModel):
    """
    Sections được emit TRƯỚC khi token streaming bắt đầu.
    Frontend render section skeletons ngay lập tức.
    """
    type:     str        = "sections"
    sections: list[dict] = []


class SSEDoneEvent(BaseModel):
    """Final event — complete message với tất cả structured data."""
    type:    str             = "done"
    message: MessageResponse


class SSEErrorEvent(BaseModel):
    """Pipeline thất bại."""
    type:   str = "error"
    detail: str
