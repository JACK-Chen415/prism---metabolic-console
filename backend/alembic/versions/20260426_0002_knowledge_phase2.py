"""knowledge schema and audit tables

Revision ID: 20260426_0002
Revises: 20260426_0001
Create Date: 2026-04-26 10:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260426_0002"
down_revision = "20260426_0001"
branch_labels = None
depends_on = None


source_tier_enum = postgresql.ENUM("TIER_1", "TIER_2", "TIER_3", "TIER_4", name="knowledgesourcetier")
source_type_enum = postgresql.ENUM("GUIDELINE", "CONSENSUS", "FAQ", "EDUCATION", name="knowledgesourcetype")
localization_enum = postgresql.ENUM("CN", "INTL", name="knowledgelocalization")
recommendation_enum = postgresql.ENUM(
    "RECOMMEND",
    "MODERATE",
    "LIMIT",
    "AVOID",
    "CONDITIONAL",
    "INSUFFICIENT",
    name="recommendationlevel",
)
source_confidence_enum = postgresql.ENUM("HIGH", "MEDIUM", "LOW", name="sourceconfidence")
rule_source_tier_enum = postgresql.ENUM("TIER_1", "TIER_2", "TIER_3", "TIER_4", name="rulehighestsourcetier")
condition_scope_enum = postgresql.ENUM(
    "GENERAL", "ACUTE", "STABLE", "MONITORING", "SPECIAL", name="conditionscopefield"
)
mapping_field_enum = postgresql.ENUM("CONDITION_CODE", "TITLE", name="healthconditionmappingfield")
mapping_type_enum = postgresql.ENUM("EXACT", "NORMALIZED", "ALIAS", "CONTAINS", name="healthconditionmappingtype")
knowledge_origin_enum = postgresql.ENUM(
    "LOCAL_RULE", "LOCAL_KNOWLEDGE", "CLOUD_SUPPLEMENT", "MIXED", name="knowledgeorigin"
)
fallback_status_enum = postgresql.ENUM(
    "LOCAL_COMPLETE",
    "LOCAL_PARTIAL_ALLOW_CLOUD",
    "LOCAL_BLOCKED_NO_CLOUD",
    "NO_LOCAL_MATCH_ALLOW_CLOUD",
    name="knowledgefallbackstatus",
)
audit_recommendation_enum = postgresql.ENUM(
    "RECOMMEND",
    "MODERATE",
    "LIMIT",
    "AVOID",
    "CONDITIONAL",
    "INSUFFICIENT",
    name="auditrecommendationlevel",
)

source_tier_enum_ref = postgresql.ENUM("TIER_1", "TIER_2", "TIER_3", "TIER_4", name="knowledgesourcetier", create_type=False)
source_type_enum_ref = postgresql.ENUM("GUIDELINE", "CONSENSUS", "FAQ", "EDUCATION", name="knowledgesourcetype", create_type=False)
localization_enum_ref = postgresql.ENUM("CN", "INTL", name="knowledgelocalization", create_type=False)
recommendation_enum_ref = postgresql.ENUM(
    "RECOMMEND",
    "MODERATE",
    "LIMIT",
    "AVOID",
    "CONDITIONAL",
    "INSUFFICIENT",
    name="recommendationlevel",
    create_type=False,
)
source_confidence_enum_ref = postgresql.ENUM("HIGH", "MEDIUM", "LOW", name="sourceconfidence", create_type=False)
rule_source_tier_enum_ref = postgresql.ENUM("TIER_1", "TIER_2", "TIER_3", "TIER_4", name="rulehighestsourcetier", create_type=False)
condition_scope_enum_ref = postgresql.ENUM(
    "GENERAL",
    "ACUTE",
    "STABLE",
    "MONITORING",
    "SPECIAL",
    name="conditionscopefield",
    create_type=False,
)
mapping_field_enum_ref = postgresql.ENUM("CONDITION_CODE", "TITLE", name="healthconditionmappingfield", create_type=False)
mapping_type_enum_ref = postgresql.ENUM("EXACT", "NORMALIZED", "ALIAS", "CONTAINS", name="healthconditionmappingtype", create_type=False)
knowledge_origin_enum_ref = postgresql.ENUM(
    "LOCAL_RULE",
    "LOCAL_KNOWLEDGE",
    "CLOUD_SUPPLEMENT",
    "MIXED",
    name="knowledgeorigin",
    create_type=False,
)
fallback_status_enum_ref = postgresql.ENUM(
    "LOCAL_COMPLETE",
    "LOCAL_PARTIAL_ALLOW_CLOUD",
    "LOCAL_BLOCKED_NO_CLOUD",
    "NO_LOCAL_MATCH_ALLOW_CLOUD",
    name="knowledgefallbackstatus",
    create_type=False,
)
audit_recommendation_enum_ref = postgresql.ENUM(
    "RECOMMEND",
    "MODERATE",
    "LIMIT",
    "AVOID",
    "CONDITIONAL",
    "INSUFFICIENT",
    name="auditrecommendationlevel",
    create_type=False,
)


def upgrade() -> None:
    source_tier_enum.create(op.get_bind(), checkfirst=True)
    source_type_enum.create(op.get_bind(), checkfirst=True)
    localization_enum.create(op.get_bind(), checkfirst=True)
    recommendation_enum.create(op.get_bind(), checkfirst=True)
    source_confidence_enum.create(op.get_bind(), checkfirst=True)
    rule_source_tier_enum.create(op.get_bind(), checkfirst=True)
    condition_scope_enum.create(op.get_bind(), checkfirst=True)
    mapping_field_enum.create(op.get_bind(), checkfirst=True)
    mapping_type_enum.create(op.get_bind(), checkfirst=True)
    knowledge_origin_enum.create(op.get_bind(), checkfirst=True)
    fallback_status_enum.create(op.get_bind(), checkfirst=True)
    audit_recommendation_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "diseases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("disease_code", sa.String(length=100), nullable=False),
        sa.Column("name_zh", sa.String(length=100), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("risk_note", sa.Text(), nullable=True),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("disease_code", name="uq_diseases_code"),
    )
    op.create_index("ix_diseases_disease_code", "diseases", ["disease_code"], unique=True)

    op.create_table(
        "food_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("food_code", sa.String(length=100), nullable=False),
        sa.Column("name_zh", sa.String(length=100), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("common_units_json", sa.JSON(), nullable=False),
        sa.Column("calories_per_100g", sa.Float(), nullable=True),
        sa.Column("protein_per_100g", sa.Float(), nullable=True),
        sa.Column("carbs_per_100g", sa.Float(), nullable=True),
        sa.Column("fat_per_100g", sa.Float(), nullable=True),
        sa.Column("fiber_per_100g", sa.Float(), nullable=True),
        sa.Column("sodium_per_100g", sa.Float(), nullable=True),
        sa.Column("purine_per_100g", sa.Float(), nullable=True),
        sa.Column("allergen_tags_json", sa.JSON(), nullable=False),
        sa.Column("risk_tags_json", sa.JSON(), nullable=False),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("food_code", name="uq_food_items_code"),
    )
    op.create_index("ix_food_items_food_code", "food_items", ["food_code"], unique=True)
    op.create_index("ix_food_items_category", "food_items", ["category"], unique=False)

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_code", sa.String(length=120), nullable=False),
        sa.Column("issuing_body", sa.String(length=255), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=False),
        sa.Column("source_year", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=True),
        sa.Column("source_type", source_type_enum_ref, nullable=False),
        sa.Column("source_tier", source_tier_enum_ref, nullable=False),
        sa.Column("evidence_level", sa.String(length=100), nullable=True),
        sa.Column("localization", localization_enum_ref, nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("document_no", sa.String(length=100), nullable=True),
        sa.Column("applicable_disease_codes_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("source_code", name="uq_knowledge_sources_code"),
    )
    op.create_index("ix_knowledge_sources_source_code", "knowledge_sources", ["source_code"], unique=True)

    op.create_table(
        "disease_food_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_code", sa.String(length=200), nullable=False),
        sa.Column("disease_code", sa.String(length=100), nullable=False),
        sa.Column("food_code", sa.String(length=100), nullable=False),
        sa.Column("recommendation_level", recommendation_enum_ref, nullable=False),
        sa.Column("portion_guidance", sa.Text(), nullable=True),
        sa.Column("frequency_guidance", sa.Text(), nullable=True),
        sa.Column("summary_note", sa.Text(), nullable=False),
        sa.Column("needs_warning", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_confidence", source_confidence_enum_ref, nullable=False),
        sa.Column("conflict_note", sa.Text(), nullable=True),
        sa.Column("caution_note", sa.Text(), nullable=True),
        sa.Column("highest_source_tier", rule_source_tier_enum_ref, nullable=False),
        sa.Column("primary_source_code", sa.String(length=120), nullable=True),
        sa.Column("condition_scope", condition_scope_enum_ref, nullable=False, server_default="GENERAL"),
        sa.Column("applicability_note", sa.Text(), nullable=True),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("source_version_snapshot", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["disease_code"], ["diseases.disease_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["food_code"], ["food_items.food_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_source_code"], ["knowledge_sources.source_code"], ondelete="SET NULL"),
        sa.UniqueConstraint("rule_code", name="uq_disease_food_rules_code"),
        sa.UniqueConstraint("disease_code", "food_code", name="uq_disease_food_rule_pair"),
    )
    op.create_index("ix_disease_food_rules_rule_code", "disease_food_rules", ["rule_code"], unique=True)
    op.create_index("ix_disease_food_rules_disease_code", "disease_food_rules", ["disease_code"], unique=False)
    op.create_index("ix_disease_food_rules_food_code", "disease_food_rules", ["food_code"], unique=False)

    op.create_table(
        "health_condition_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mapping_code", sa.String(length=200), nullable=False),
        sa.Column("source_field", mapping_field_enum_ref, nullable=False),
        sa.Column("match_type", mapping_type_enum_ref, nullable=False),
        sa.Column("match_value", sa.String(length=200), nullable=False),
        sa.Column("normalized_disease_code", sa.String(length=100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["normalized_disease_code"], ["diseases.disease_code"], ondelete="CASCADE"),
        sa.UniqueConstraint("mapping_code", name="uq_health_condition_mappings_code"),
    )
    op.create_index("ix_health_condition_mappings_mapping_code", "health_condition_mappings", ["mapping_code"], unique=True)
    op.create_index(
        "ix_health_condition_mappings_normalized_disease_code",
        "health_condition_mappings",
        ["normalized_disease_code"],
        unique=False,
    )

    op.create_table(
        "rule_source_maps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_code", sa.String(length=200), nullable=False),
        sa.Column("source_code", sa.String(length=120), nullable=False),
        sa.Column("citation_rank", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("section_ref", sa.String(length=255), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("seed_version", sa.String(length=50), nullable=False, server_default="core_v1"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["rule_code"], ["disease_food_rules.rule_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_code"], ["knowledge_sources.source_code"], ondelete="CASCADE"),
        sa.UniqueConstraint("rule_code", "source_code", "section_ref", name="uq_rule_source_section"),
    )
    op.create_index("ix_rule_source_maps_rule_code", "rule_source_maps", ["rule_code"], unique=False)
    op.create_index("ix_rule_source_maps_source_code", "rule_source_maps", ["source_code"], unique=False)

    op.create_table(
        "knowledge_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("route_name", sa.String(length=100), nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=True),
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("query_excerpt", sa.String(length=500), nullable=True),
        sa.Column("origin", knowledge_origin_enum_ref, nullable=False),
        sa.Column("fallback_status", fallback_status_enum_ref, nullable=False),
        sa.Column("matched_disease_codes_json", sa.JSON(), nullable=False),
        sa.Column("matched_food_codes_json", sa.JSON(), nullable=False),
        sa.Column("unmapped_conditions_json", sa.JSON(), nullable=False),
        sa.Column("local_decision_level", audit_recommendation_enum_ref, nullable=True),
        sa.Column("called_cloud", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cloud_call_reason", sa.Text(), nullable=True),
        sa.Column("cloud_blocked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_knowledge_audit_logs_user_id", "knowledge_audit_logs", ["user_id"], unique=False)
    op.create_index("ix_knowledge_audit_logs_route_name", "knowledge_audit_logs", ["route_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_audit_logs_route_name", table_name="knowledge_audit_logs")
    op.drop_index("ix_knowledge_audit_logs_user_id", table_name="knowledge_audit_logs")
    op.drop_table("knowledge_audit_logs")
    op.drop_index("ix_rule_source_maps_source_code", table_name="rule_source_maps")
    op.drop_index("ix_rule_source_maps_rule_code", table_name="rule_source_maps")
    op.drop_table("rule_source_maps")
    op.drop_index("ix_health_condition_mappings_normalized_disease_code", table_name="health_condition_mappings")
    op.drop_index("ix_health_condition_mappings_mapping_code", table_name="health_condition_mappings")
    op.drop_table("health_condition_mappings")
    op.drop_index("ix_disease_food_rules_food_code", table_name="disease_food_rules")
    op.drop_index("ix_disease_food_rules_disease_code", table_name="disease_food_rules")
    op.drop_index("ix_disease_food_rules_rule_code", table_name="disease_food_rules")
    op.drop_table("disease_food_rules")
    op.drop_index("ix_knowledge_sources_source_code", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.drop_index("ix_food_items_category", table_name="food_items")
    op.drop_index("ix_food_items_food_code", table_name="food_items")
    op.drop_table("food_items")
    op.drop_index("ix_diseases_disease_code", table_name="diseases")
    op.drop_table("diseases")

    audit_recommendation_enum.drop(op.get_bind(), checkfirst=True)
    fallback_status_enum.drop(op.get_bind(), checkfirst=True)
    knowledge_origin_enum.drop(op.get_bind(), checkfirst=True)
    mapping_type_enum.drop(op.get_bind(), checkfirst=True)
    mapping_field_enum.drop(op.get_bind(), checkfirst=True)
    condition_scope_enum.drop(op.get_bind(), checkfirst=True)
    rule_source_tier_enum.drop(op.get_bind(), checkfirst=True)
    source_confidence_enum.drop(op.get_bind(), checkfirst=True)
    recommendation_enum.drop(op.get_bind(), checkfirst=True)
    localization_enum.drop(op.get_bind(), checkfirst=True)
    source_type_enum.drop(op.get_bind(), checkfirst=True)
    source_tier_enum.drop(op.get_bind(), checkfirst=True)
