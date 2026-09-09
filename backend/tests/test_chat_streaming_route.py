import pytest

from app.api.routes import chat as chat_route
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.user import User
from app.schemas.chat import ChatMessageCreate
from app.services.knowledge.contracts import KnowledgeSummary, LocalDecision


class FakeScalarResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeExecuteResult:
    def __init__(self, *, scalar=None, items=None):
        self.scalar = scalar
        self.items = items or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return FakeScalarResult(self.items)


class FakeDb:
    def __init__(self):
        self.execute_calls = 0
        self.messages = []
        self.next_message_id = 1

    async def execute(self, _query):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return FakeExecuteResult(scalar=ChatSession(id=1, user_id=1, title="test"))
        if self.execute_calls == 2:
            return FakeExecuteResult(items=self.messages)
        if self.execute_calls == 3:
            return FakeExecuteResult(items=[])
        return FakeExecuteResult(items=[])

    def add(self, item):
        if isinstance(item, ChatMessage):
            item.id = self.next_message_id
            self.next_message_id += 1
            if item.role == MessageRole.USER:
                self.messages.append(item)
            else:
                self.messages.append(item)

    async def flush(self):
        return None

    async def refresh(self, _item):
        return None


class LocalKnowledgeService:
    async def summarize_query_for_user(self, *_args, **kwargs):
        decision = LocalDecision(
            food_code="beer",
            food_name="啤酒",
            recommendation_level=RecommendationLevel.AVOID,
            matched_disease_codes=["gout"],
            summary="痛风场景下应避免饮酒。",
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
        )
        return KnowledgeSummary(
            query=kwargs["query"],
            matched_disease_codes=["gout"],
            matched_food_codes=["beer"],
            summary="命中本地规则",
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
            can_call_cloud=False,
            local_decisions=[decision],
        )

    def render_local_markdown(self, _summary):
        return "本地规则：痛风场景下不建议喝啤酒。"

    def build_local_guardrail(self, _summary):
        return "本地规则优先"


class CloudKnowledgeService(LocalKnowledgeService):
    async def summarize_query_for_user(self, *_args, **kwargs):
        return KnowledgeSummary(
            query=kwargs["query"],
            summary="本地知识未命中明确规则",
            origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
            fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
            can_call_cloud=True,
            local_decisions=[],
        )


class FakeDoubaoService:
    async def chat(self, *_args, **kwargs):
        metrics = kwargs.get("metrics")
        if metrics is not None:
            metrics.update(
                {
                    "prompt_build_ms": 1.0,
                    "prompt_chars": 100,
                    "message_count": 2,
                    "doubao_total_ms": 2.0,
                    "response_chars": 4,
                }
            )

        async def stream():
            yield "云端"
            yield "回复"

        return stream()


async def fake_audit(*_args, **_kwargs):
    return object()


async def collect_stream(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_stream_route_returns_local_rule_answer(monkeypatch):
    monkeypatch.setattr(chat_route, "knowledge_service", LocalKnowledgeService())
    monkeypatch.setattr(chat_route, "write_knowledge_audit_log", fake_audit)

    response = await chat_route.send_message_stream(
        1,
        ChatMessageCreate(content="痛风能喝啤酒吗"),
        User(id=1, phone="13800138000", password_hash="x"),
        FakeDb(),
    )

    body = await collect_stream(response)

    assert "event: meta" in body
    assert "event: delta" in body
    assert "本地规则" in body
    assert "event: done" in body
    assert "LOCAL_BLOCKED_NO_CLOUD" in body


@pytest.mark.asyncio
async def test_stream_route_can_proxy_cloud_chunks(monkeypatch):
    monkeypatch.setattr(chat_route, "knowledge_service", CloudKnowledgeService())
    monkeypatch.setattr(chat_route, "doubao_service", FakeDoubaoService())
    monkeypatch.setattr(chat_route, "write_knowledge_audit_log", fake_audit)

    response = await chat_route.send_message_stream(
        1,
        ChatMessageCreate(content="晚餐怎么搭配"),
        User(id=1, phone="13800138001", password_hash="x"),
        FakeDb(),
    )

    body = await collect_stream(response)

    assert body.count("event: delta") == 2
    assert "云端" in body
    assert "回复" in body
    assert "event: done" in body
    assert "NO_LOCAL_MATCH_ALLOW_CLOUD" in body
