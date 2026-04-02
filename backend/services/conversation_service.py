"""
Conversation Service — in-memory conversation store.

Lưu ý: Dữ liệu mất khi restart server. Đây là thiết kế có chủ ý cho
phiên bản hiện tại — toàn bộ state được giữ trên client (frontend seed data)
và sync lại qua API. Không cần persistence cho hackathon scope này.

Nếu cần persistence: thay _store bằng Redis hoặc SQLite với SQLAlchemy.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    id:         str
    role:       str           # "user" | "assistant"
    content:    str
    citations:  list = field(default_factory=list)
    metadata:   dict = field(default_factory=dict)
    created_at: str  = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Conversation:
    id:         str
    title:      str
    mode:       str           # "standard" | "agentic"
    messages:   list[Message] = field(default_factory=list)
    created_at: str           = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ConversationService:
    def __init__(self):
        self._store: dict[str, Conversation] = {}

    def create(self, title: str = "", mode: str = "standard") -> Conversation:
        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        conv    = Conversation(
            id    = conv_id,
            title = title or "Cuộc hội thoại mới",
            mode  = mode,
        )
        self._store[conv_id] = conv
        return conv

    def get(self, conv_id: str) -> Conversation | None:
        return self._store.get(conv_id)

    def list_all(self) -> list[Conversation]:
        return sorted(
            self._store.values(),
            key=lambda c: c.created_at,
            reverse=True,
        )

    def add_message(self, conv_id: str, message: Message) -> bool:
        conv = self._store.get(conv_id)
        if not conv:
            return False
        conv.messages.append(message)
        return True

    def update_title(self, conv_id: str, title: str):
        conv = self._store.get(conv_id)
        if conv:
            conv.title = title

    def get_recent_messages(self, conv_id: str, n: int = 6) -> list[Message]:
        """Lấy n messages gần nhất, dùng để build conversation history cho pipeline."""
        conv = self._store.get(conv_id)
        if not conv:
            return []
        return conv.messages[-n:] if len(conv.messages) > n else conv.messages[:]
