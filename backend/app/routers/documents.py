"""
Document viewer router — serve law articles for the source panel.
"""
from fastapi import APIRouter, Request, HTTPException
from backend.app.schemas import DieuResponse, KhoanResponse, DocumentInfoResponse

router = APIRouter(tags=["documents"])


@router.get("/api/documents/{van_ban_id}", response_model=DocumentInfoResponse)
async def get_document_info(van_ban_id: str, request: Request):
    doc_svc = request.app.state.documents
    if not doc_svc or doc_svc.van_ban_id != van_ban_id:
        raise HTTPException(404, f"Document '{van_ban_id}' not found")
    info = doc_svc.get_document_info()
    return DocumentInfoResponse(**info)


@router.get("/api/documents/{van_ban_id}/dieu/{so_dieu}", response_model=DieuResponse)
async def get_dieu(van_ban_id: str, so_dieu: int, request: Request):
    doc_svc = request.app.state.documents
    if not doc_svc or doc_svc.van_ban_id != van_ban_id:
        raise HTTPException(404, f"Document '{van_ban_id}' not found")

    chunk = doc_svc.get_dieu(so_dieu)
    if not chunk:
        raise HTTPException(404, f"Điều {so_dieu} not found")

    # Build khoan list
    khoan_list = []
    for k in chunk.get("khoan", []):
        khoan_list.append(KhoanResponse(
            so_khoan=k.get("so_khoan", 0),
            noi_dung=k.get("noi_dung", ""),
            diem=k.get("diem", []),
        ))

    return DieuResponse(
        van_ban_id=van_ban_id,
        van_ban_name=doc_svc.document.get("ten_van_ban", ""),
        so_dieu=chunk["so_dieu"],
        ten_dieu=chunk["ten_dieu"],
        chuong_so=chunk["chuong_so"],
        ten_chuong=chunk["ten_chuong"],
        noi_dung=chunk["noi_dung"],
        khoan=khoan_list,
        references=chunk.get("references", []),
        entities=chunk.get("entities", []),
    )
