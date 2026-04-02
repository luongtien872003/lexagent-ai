"""
Document Service — serve extractor JSON chunks for the source viewer.
Pre-loads at startup, O(1) lookup by so_dieu.
"""
import json
from pathlib import Path


class DocumentService:
    def __init__(self, json_path: str | Path):
        json_path = Path(json_path)
        if not json_path.exists():
            raise FileNotFoundError(f"Extractor JSON not found: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        self.document = data["document"]
        self._chunks = data["chunks"]

        # Index dieu chunks by so_dieu for O(1) lookup
        self._by_dieu: dict[int, dict] = {}
        for c in self._chunks:
            if c["type"] == "dieu":
                self._by_dieu[c["so_dieu"]] = c

        print(f"[DocumentService] Loaded: {self.document['so_hieu']} "
              f"— {len(self._by_dieu)} điều")

    @property
    def van_ban_id(self) -> str:
        return self.document["id"]

    @property
    def dieu_count(self) -> int:
        return len(self._by_dieu)

    def get_document_info(self) -> dict:
        return self.document

    def get_dieu(self, so_dieu: int) -> dict | None:
        return self._by_dieu.get(so_dieu)

    def get_all_dieu_numbers(self) -> list[int]:
        return sorted(self._by_dieu.keys())
