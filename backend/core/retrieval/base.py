"""Base types cho retrieval layer v2."""
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class RetrievedChunk:
    chunk_id:       str
    so_dieu:        int
    ten_dieu:       str
    chuong_so:      int
    ten_chuong:     str
    noi_dung:       str
    score:          float
    source:         str
    # v2 multi-law
    law_id:         str = "unknown"
    khoan_so:       int = 0
    loai_van_ban:   str = "luat"
    thu_tu_uu_tien: int = 1
    ngay_hieu_luc:  str = ""
    context_header: str = ""
    parent_dieu_id: str = ""
    so_hieu:        str = ""


class BaseRetriever(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        law_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]: ...
