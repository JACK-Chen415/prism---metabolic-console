import pytest

from app.core.security import hash_sensitive_value
from app.models.knowledge import FallbackStatus, KnowledgeOrigin
from app.services.knowledge.audit import write_knowledge_audit_log


class FakeAuditDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_knowledge_audit_stores_query_hash_not_raw_health_text():
    db = FakeAuditDb()
    raw_query = "我有痛风和虾过敏，今天能不能吃花生酱鸡丁？"

    row = await write_knowledge_audit_log(
        db,
        user_id=1,
        route_name="/api/intake/confirm",
        origin=KnowledgeOrigin.LOCAL_RULE,
        fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
        matched_disease_codes=["gout"],
        matched_food_codes=["kung_pao_chicken"],
        query_excerpt=raw_query,
    )

    assert db.added == [row]
    assert db.flush_count == 1
    assert row.query_excerpt == hash_sensitive_value(raw_query)
    assert raw_query not in str(row.query_excerpt)
