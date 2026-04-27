"""Structured local knowledge and rule models."""

from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RecommendationLevel(str, enum.Enum):
    RECOMMEND = "RECOMMEND"
    MODERATE = "MODERATE"
    LIMIT = "LIMIT"
    AVOID = "AVOID"
    CONDITIONAL = "CONDITIONAL"
    INSUFFICIENT = "INSUFFICIENT"


class SourceTier(str, enum.Enum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    TIER_4 = "TIER_4"


class SourceType(str, enum.Enum):
    GUIDELINE = "GUIDELINE"
    CONSENSUS = "CONSENSUS"
    FAQ = "FAQ"
    EDUCATION = "EDUCATION"


class Localization(str, enum.Enum):
    CN = "CN"
    INTL = "INTL"


class SourceConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class KnowledgeOrigin(str, enum.Enum):
    LOCAL_RULE = "LOCAL_RULE"
    LOCAL_KNOWLEDGE = "LOCAL_KNOWLEDGE"
    CLOUD_SUPPLEMENT = "CLOUD_SUPPLEMENT"
    MIXED = "MIXED"


class FallbackStatus(str, enum.Enum):
    LOCAL_COMPLETE = "LOCAL_COMPLETE"
    LOCAL_PARTIAL_ALLOW_CLOUD = "LOCAL_PARTIAL_ALLOW_CLOUD"
    LOCAL_BLOCKED_NO_CLOUD = "LOCAL_BLOCKED_NO_CLOUD"
    NO_LOCAL_MATCH_ALLOW_CLOUD = "NO_LOCAL_MATCH_ALLOW_CLOUD"


class SourceField(str, enum.Enum):
    CONDITION_CODE = "CONDITION_CODE"
    TITLE = "TITLE"


class MatchType(str, enum.Enum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    ALIAS = "ALIAS"
    CONTAINS = "CONTAINS"


class ConditionScopeField(str, enum.Enum):
    GENERAL = "GENERAL"
    ACUTE = "ACUTE"
    STABLE = "STABLE"
    MONITORING = "MONITORING"
    SPECIAL = "SPECIAL"


class Disease(Base):
    __tablename__ = "diseases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    disease_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(100), nullable=False)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FoodItem(Base):
    __tablename__ = "food_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    food_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(100), nullable=False)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    common_units_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    calories_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    protein_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    carbs_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    fat_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    fiber_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    sodium_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    purine_per_100g: Mapped[Optional[float]] = mapped_column(nullable=True)
    allergen_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    issuing_body: Mapped[str] = mapped_column(String(255), nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType, name="knowledgesourcetype"),
        nullable=False,
    )
    source_tier: Mapped[SourceTier] = mapped_column(
        SQLEnum(SourceTier, name="knowledgesourcetier"),
        nullable=False,
    )
    evidence_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    localization: Mapped[Localization] = mapped_column(
        SQLEnum(Localization, name="knowledgelocalization"),
        nullable=False,
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    document_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    applicable_disease_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DiseaseFoodRule(Base):
    __tablename__ = "disease_food_rules"
    __table_args__ = (
        UniqueConstraint("disease_code", "food_code", name="uq_disease_food_rule_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    disease_code: Mapped[str] = mapped_column(
        ForeignKey("diseases.disease_code", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    food_code: Mapped[str] = mapped_column(
        ForeignKey("food_items.food_code", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recommendation_level: Mapped[RecommendationLevel] = mapped_column(
        SQLEnum(RecommendationLevel, name="recommendationlevel"),
        nullable=False,
    )
    portion_guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frequency_guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_note: Mapped[str] = mapped_column(Text, nullable=False)
    needs_warning: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_confidence: Mapped[SourceConfidence] = mapped_column(
        SQLEnum(SourceConfidence, name="sourceconfidence"),
        nullable=False,
    )
    conflict_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    highest_source_tier: Mapped[SourceTier] = mapped_column(
        SQLEnum(SourceTier, name="rulehighestsourcetier"),
        nullable=False,
    )
    primary_source_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_sources.source_code", ondelete="SET NULL"),
        nullable=True,
    )
    condition_scope: Mapped[ConditionScopeField] = mapped_column(
        SQLEnum(ConditionScopeField, name="conditionscopefield"),
        default=ConditionScopeField.GENERAL,
        nullable=False,
    )
    applicability_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    source_version_snapshot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class RuleSourceMap(Base):
    __tablename__ = "rule_source_maps"
    __table_args__ = (
        UniqueConstraint("rule_code", "source_code", "section_ref", name="uq_rule_source_section"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(
        ForeignKey("disease_food_rules.rule_code", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_code: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.source_code", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    citation_rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    section_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    source_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class HealthConditionMapping(Base):
    __tablename__ = "health_condition_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mapping_code: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    source_field: Mapped[SourceField] = mapped_column(
        SQLEnum(SourceField, name="healthconditionmappingfield"),
        nullable=False,
    )
    match_type: Mapped[MatchType] = mapped_column(
        SQLEnum(MatchType, name="healthconditionmappingtype"),
        nullable=False,
    )
    match_value: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_disease_code: Mapped[str] = mapped_column(
        ForeignKey("diseases.disease_code", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    seed_version: Mapped[str] = mapped_column(String(50), default="core_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeAuditLog(Base):
    __tablename__ = "knowledge_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    route_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    chat_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    query_excerpt: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    origin: Mapped[KnowledgeOrigin] = mapped_column(
        SQLEnum(KnowledgeOrigin, name="knowledgeorigin"),
        nullable=False,
    )
    fallback_status: Mapped[FallbackStatus] = mapped_column(
        SQLEnum(FallbackStatus, name="knowledgefallbackstatus"),
        nullable=False,
    )
    matched_disease_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_food_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    unmapped_conditions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    local_decision_level: Mapped[Optional[RecommendationLevel]] = mapped_column(
        SQLEnum(RecommendationLevel, name="auditrecommendationlevel"),
        nullable=True,
    )
    called_cloud: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cloud_call_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cloud_blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="knowledge_audit_logs")
