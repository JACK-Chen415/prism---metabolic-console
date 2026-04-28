import asyncio

from app.models.knowledge import (
    Disease,
    DiseaseFoodRule,
    FoodItem,
    HealthConditionMapping,
    KnowledgeSource,
    RuleSourceMap,
)
from app.seed import knowledge_seed as seed_module
from app.seed.knowledge_seed import load_dataset, upsert_seed, validate_dataset


def test_core_v1_dataset_validation_passes():
    dataset = load_dataset("core_v1")
    validate_dataset(dataset)


def test_upsert_seed_flushes_parent_tables_before_rules(monkeypatch):
    dataset = load_dataset("core_v1")
    events: list[str] = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self):
            events.append("flush")

        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    async def fake_upsert_rows(session, *, model, rows, key_fields, summary, defaults):
        events.append(model.__name__)

    monkeypatch.setattr(seed_module, "async_session_maker", lambda: FakeSession())
    monkeypatch.setattr(seed_module, "_upsert_rows", fake_upsert_rows)

    asyncio.run(upsert_seed(dataset, dry_run=False, disable_missing=False))

    assert events == [
        Disease.__name__,
        FoodItem.__name__,
        KnowledgeSource.__name__,
        HealthConditionMapping.__name__,
        "flush",
        DiseaseFoodRule.__name__,
        "flush",
        RuleSourceMap.__name__,
        "flush",
        "commit",
    ]
