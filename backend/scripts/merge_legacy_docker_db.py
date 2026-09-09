"""Merge legacy Docker Postgres data into the local canonical database.

The legacy Docker database is queried through ``docker exec`` because the old
container may not expose a usable host password. The target database is the
local PostgreSQL instance used by the app after the database unification work.

The script is intentionally idempotent:
- users are matched by phone;
- meals are matched by (user_id, client_id);
- chat sessions/messages use stable content/timestamp checks;
- existing non-null profile fields are not overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import asyncpg


TABLES = (
    "users",
    "health_conditions",
    "meals",
    "chat_sessions",
    "chat_messages",
    "app_messages",
)

DEFAULT_TARGET_URL = "postgresql://prism:prism123@127.0.0.1:5433/prism_metabolic"

UPDATE_FIELD_CASTS = {
    "gender": "::gender",
    "last_login_at": "::timestamptz",
}


def normalize_target_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    return url


def fetch_legacy_rows(table: str) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ValueError(f"Unsupported legacy table: {table}")

    sql = (
        "COPY ("
        f"SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY id) t"
        ") TO STDOUT"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "prism_db",
            "psql",
            "-U",
            "postgres",
            "-d",
            "prism_db",
            "-At",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def json_param(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def timestamp_param(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(f"Unsupported timestamp value: {value!r}")


def date_param(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Unsupported date value: {value!r}")


def chat_role_param(value: Any) -> str:
    role = str(value)
    return {
        "USER": "user",
        "ASSISTANT": "assistant",
        "SYSTEM": "system",
    }.get(role, role)


def first_present(row: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


async def merge_users(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> tuple[dict[int, int], dict[str, int]]:
    user_map: dict[int, int] = {}
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    for row in rows:
        old_id = row["id"]
        existing = await conn.fetchrow("select * from users where phone = $1", row["phone"])
        if existing:
            user_map[old_id] = existing["id"]
            updates: dict[str, Any] = {}
            for field in ("nickname", "avatar_url", "gender", "age", "height", "weight", "last_login_at"):
                legacy_value = row.get(field)
                if existing[field] is None and legacy_value is not None:
                    updates[field] = timestamp_param(legacy_value) if field == "last_login_at" else legacy_value
            if updates:
                set_sql = ", ".join(
                    f"{field} = ${index}{UPDATE_FIELD_CASTS.get(field, '')}"
                    for index, field in enumerate(updates, start=2)
                )
                await conn.execute(
                    f"update users set {set_sql}, updated_at = now() where id = $1",
                    existing["id"],
                    *updates.values(),
                )
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
            continue

        new_id = await conn.fetchval(
            """
            insert into users (
                phone, password_hash, nickname, avatar_url, gender, age, height,
                weight, is_active, is_verified, created_at, updated_at, last_login_at
            )
            values (
                $1, $2, $3, $4, $5::gender, $6, $7, $8, coalesce($9, true), coalesce($10, false),
                coalesce($11::timestamptz, now()), coalesce($12::timestamptz, now()),
                $13::timestamptz
            )
            returning id
            """,
            row["phone"],
            row["password_hash"],
            row.get("nickname"),
            row.get("avatar_url"),
            row.get("gender"),
            row.get("age"),
            row.get("height"),
            row.get("weight"),
            row.get("is_active"),
            row.get("is_verified"),
            timestamp_param(row.get("created_at")),
            timestamp_param(row.get("updated_at")),
            timestamp_param(row.get("last_login_at")),
        )
        user_map[old_id] = new_id
        stats["inserted"] += 1

    return user_map, stats


async def merge_health_conditions(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    user_map: dict[int, int],
) -> dict[str, int]:
    stats = {"inserted": 0, "skipped": 0, "orphaned": 0}
    for row in rows:
        user_id = user_map.get(row["user_id"])
        if not user_id:
            stats["orphaned"] += 1
            continue
        existing_id = await conn.fetchval(
            """
            select id from health_conditions
            where user_id = $1 and condition_code = $2 and condition_type = $3::conditiontype
            limit 1
            """,
            user_id,
            row["condition_code"],
            row["condition_type"],
        )
        if existing_id:
            stats["skipped"] += 1
            continue
        await conn.execute(
            """
            insert into health_conditions (
                user_id, condition_code, title, icon, condition_type, status, trend,
                value, unit, dictum, attribution, created_at, updated_at
            )
            values (
                $1, $2, $3, coalesce($4, 'medical_services'), $5::conditiontype,
                coalesce($6::conditionstatus, 'MONITORING'::conditionstatus),
                coalesce($7::trendtype, 'STABLE'::trendtype), $8, $9, $10, $11,
                coalesce($12::timestamptz, now()), coalesce($13::timestamptz, now())
            )
            """,
            user_id,
            row["condition_code"],
            row["title"],
            row.get("icon"),
            row["condition_type"],
            row.get("status"),
            row.get("trend"),
            row.get("value"),
            row.get("unit"),
            row.get("dictum"),
            row.get("attribution"),
            timestamp_param(row.get("created_at")),
            timestamp_param(row.get("updated_at")),
        )
        stats["inserted"] += 1
    return stats


async def merge_meals(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    user_map: dict[int, int],
) -> dict[str, int]:
    stats = {"inserted": 0, "skipped": 0, "orphaned": 0}
    for row in rows:
        user_id = user_map.get(row["user_id"])
        if not user_id:
            stats["orphaned"] += 1
            continue
        client_id = row.get("client_id") or f"legacy-docker-meal-{row['id']}"
        existing_id = await conn.fetchval(
            "select id from meals where user_id = $1 and client_id = $2",
            user_id,
            client_id,
        )
        if existing_id:
            stats["skipped"] += 1
            continue

        ai_recognized = bool(row.get("ai_recognized"))
        source = "photo" if ai_recognized or row.get("image_url") else "manual"
        recognition_meta = {
            "legacy_import": True,
            "legacy_database": "docker:prism_db",
            "legacy_table": "meals",
            "legacy_id": row["id"],
        }

        await conn.execute(
            """
            insert into meals (
                user_id, client_id, name, portion, calories, sodium, purine, protein,
                carbs, fat, fiber, meal_type, category, record_date, note, image_url,
                ai_recognized, sync_status, source, source_detail, confidence,
                estimated_fields_json, rule_warnings_json, recognition_meta_json,
                created_at, updated_at
            )
            values (
                $1, $2, $3, $4, coalesce($5, 0), coalesce($6, 0), coalesce($7, 0),
                $8, $9, $10, $11, $12::mealtype, $13::foodcategory, $14::date, $15, $16,
                coalesce($17, false), coalesce($18::syncstatus, 'SYNCED'::syncstatus),
                $19, 'legacy_docker_import', $20,
                '[]'::json, '[]'::json, $21::json,
                coalesce($22::timestamptz, now()), coalesce($23::timestamptz, now())
            )
            """,
            user_id,
            client_id,
            row["name"],
            row["portion"],
            row.get("calories"),
            row.get("sodium"),
            row.get("purine"),
            row.get("protein"),
            row.get("carbs"),
            row.get("fat"),
            row.get("fiber"),
            row["meal_type"],
            row["category"],
            date_param(row["record_date"]),
            row.get("note"),
            row.get("image_url"),
            row.get("ai_recognized"),
            row.get("sync_status"),
            source,
            None,
            json_param(recognition_meta),
            timestamp_param(row.get("created_at")),
            timestamp_param(row.get("updated_at")),
        )
        stats["inserted"] += 1
    return stats


async def merge_chat_sessions(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    user_map: dict[int, int],
) -> tuple[dict[int, int], dict[str, int]]:
    session_map: dict[int, int] = {}
    stats = {"inserted": 0, "skipped": 0, "orphaned": 0}
    for row in rows:
        user_id = user_map.get(row["user_id"])
        if not user_id:
            stats["orphaned"] += 1
            continue
        existing_id = await conn.fetchval(
            """
            select id from chat_sessions
            where user_id = $1 and title = $2 and created_at = $3::timestamptz
            limit 1
            """,
            user_id,
            row["title"],
            timestamp_param(row.get("created_at")),
        )
        if existing_id:
            session_map[row["id"]] = existing_id
            stats["skipped"] += 1
            continue
        new_id = await conn.fetchval(
            """
            insert into chat_sessions (user_id, title, created_at, updated_at)
            values (
                $1, coalesce($2, 'legacy conversation'),
                coalesce($3::timestamptz, now()),
                coalesce($4::timestamptz, now())
            )
            returning id
            """,
            user_id,
            row.get("title"),
            timestamp_param(row.get("created_at")),
            timestamp_param(row.get("updated_at")),
        )
        session_map[row["id"]] = new_id
        stats["inserted"] += 1
    return session_map, stats


async def merge_chat_messages(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    session_map: dict[int, int],
) -> dict[str, int]:
    stats = {"inserted": 0, "skipped": 0, "orphaned": 0}
    for row in rows:
        session_id = session_map.get(row["session_id"])
        if not session_id:
            stats["orphaned"] += 1
            continue
        existing_id = await conn.fetchval(
            """
            select id from chat_messages
            where session_id = $1 and role = $2::messagerole and content = $3
              and created_at = $4::timestamptz
            limit 1
            """,
            session_id,
            chat_role_param(row["role"]),
            row["content"],
            timestamp_param(row.get("created_at")),
        )
        if existing_id:
            stats["skipped"] += 1
            continue
        await conn.execute(
            """
            insert into chat_messages (
                session_id, role, content, attachments, model, tokens_used, created_at
            )
            values (
                $1, $2::messagerole, $3, $4::json, $5, $6, coalesce($7::timestamptz, now())
            )
            """,
            session_id,
            chat_role_param(row["role"]),
            row["content"],
            json_param(row.get("attachments")),
            row.get("model"),
            row.get("tokens_used"),
            timestamp_param(row.get("created_at")),
        )
        stats["inserted"] += 1
    return stats


async def merge_app_messages(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    user_map: dict[int, int],
) -> dict[str, int]:
    stats = {"inserted": 0, "skipped": 0, "orphaned": 0}
    for row in rows:
        user_id = user_map.get(row["user_id"])
        if not user_id:
            stats["orphaned"] += 1
            continue
        existing_id = await conn.fetchval(
            """
            select id from app_messages
            where user_id = $1 and title = $2 and content = $3
              and created_at = $4::timestamptz
            limit 1
            """,
            user_id,
            row["title"],
            row["content"],
            timestamp_param(row.get("created_at")),
        )
        if existing_id:
            stats["skipped"] += 1
            continue
        await conn.execute(
            """
            insert into app_messages (
                user_id, message_type, title, content, attribution, is_read,
                created_at, read_at
            )
            values (
                $1, $2::messagetype, $3, $4, $5, coalesce($6, false),
                coalesce($7::timestamptz, now()), $8::timestamptz
            )
            """,
            user_id,
            row["message_type"],
            row["title"],
            row["content"],
            row.get("attribution"),
            row.get("is_read"),
            timestamp_param(row.get("created_at")),
            timestamp_param(row.get("read_at")),
        )
        stats["inserted"] += 1
    return stats


async def reset_sequences(conn: asyncpg.Connection) -> None:
    for table in TABLES:
        await conn.execute(
            """
            select setval(
                pg_get_serial_sequence($1, 'id'),
                coalesce((select max(id) from %s), 1),
                true
            )
            """
            % table,
            table,
        )


async def run_merge(target_url: str, dry_run: bool) -> dict[str, Any]:
    legacy_rows = {table: fetch_legacy_rows(table) for table in TABLES}
    target_url = normalize_target_url(target_url)
    conn = await asyncpg.connect(target_url)
    try:
        async with conn.transaction():
            user_map, users_stats = await merge_users(conn, legacy_rows["users"])
            condition_stats = await merge_health_conditions(conn, legacy_rows["health_conditions"], user_map)
            meal_stats = await merge_meals(conn, legacy_rows["meals"], user_map)
            session_map, session_stats = await merge_chat_sessions(conn, legacy_rows["chat_sessions"], user_map)
            message_stats = await merge_chat_messages(conn, legacy_rows["chat_messages"], session_map)
            app_message_stats = await merge_app_messages(conn, legacy_rows["app_messages"], user_map)
            await reset_sequences(conn)

            summary = {
                "legacy_rows": {table: len(rows) for table, rows in legacy_rows.items()},
                "users": users_stats,
                "health_conditions": condition_stats,
                "meals": meal_stats,
                "chat_sessions": session_stats,
                "chat_messages": message_stats,
                "app_messages": app_message_stats,
            }

            if dry_run:
                raise RuntimeError("__DRY_RUN_ROLLBACK__:" + json.dumps(summary, ensure_ascii=False))
            return summary
    except RuntimeError as exc:
        marker = "__DRY_RUN_ROLLBACK__:"
        if str(exc).startswith(marker):
            return json.loads(str(exc)[len(marker) :])
        raise
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge Docker legacy DB data into the local canonical DB.")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = asyncio.run(run_merge(args.target_url, args.dry_run))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
