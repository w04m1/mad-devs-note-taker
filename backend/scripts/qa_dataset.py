"""Create a repeatable 10k-note data set and emit PostgreSQL JSON query plans."""

from __future__ import annotations

import argparse
import json
from time import perf_counter

from psycopg import connect
from sqlalchemy.engine import make_url

from app.config import get_settings

SEED_SQL = """
TRUNCATE outbox_events, notifications, reminder_deliveries, reminder_rules,
 occurrence_exceptions, series_reminder_templates, series_tags, note_tags,
 notes, recurrence_series, tags, user_settings CASCADE;
INSERT INTO tags (id, name, normalized_name, color, version)
SELECT md5('tag-' || i::text)::uuid, 'QA tag ' || i, 'qa tag ' || i, '#336699', 1
FROM generate_series(1, 20) AS i;
INSERT INTO notes (id, title, body, starts_at, active, deleted_at, version)
SELECT md5('note-' || i::text)::uuid,
       CASE WHEN i % 97 = 0 THEN 'needle deterministic ' || i ELSE 'QA note ' || i END,
       'deterministic body ' || i,
       timestamptz '2026-01-01 00:00:00+00' + i * interval '5 minutes',
       i % 4 <> 0, CASE WHEN i % 50 = 0 THEN timestamptz '2026-01-01 00:00:00+00' ELSE NULL END, 1
FROM generate_series(1, 10000) AS i;
INSERT INTO note_tags (note_id, tag_id)
SELECT md5('note-' || i::text)::uuid, md5('tag-' || ((i % 20) + 1)::text)::uuid
FROM generate_series(1, 10000) AS i;
ANALYZE notes; ANALYZE note_tags;
"""

QUERIES = {
    "calendar": "SELECT id FROM notes WHERE deleted_at IS NULL AND superseded_at IS NULL AND starts_at >= timestamptz '2026-01-10' AND starts_at < timestamptz '2026-02-10' ORDER BY starts_at,id LIMIT 101",
    "search": "SELECT id FROM notes WHERE deleted_at IS NULL AND search_text ILIKE '%needle%' ORDER BY starts_at,id LIMIT 50",
    "tag_filter": "SELECT n.id FROM notes n WHERE n.deleted_at IS NULL AND n.id IN (SELECT note_id FROM note_tags WHERE tag_id=md5('tag-1')::uuid) ORDER BY n.starts_at,n.id LIMIT 50",
    "trash": "SELECT id FROM notes WHERE deleted_at IS NOT NULL AND purged_at IS NULL ORDER BY starts_at,id LIMIT 50",
}


def sync_url() -> str:
    url = make_url(get_settings().database_sync_url)
    return url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assert-max-ms", type=float, default=500.0)
    parser.add_argument("--output", default="qa-query-plans.json")
    args = parser.parse_args()
    evidence: dict[str, object] = {"rows": 10000, "queries": {}}
    with connect(sync_url()) as connection, connection.cursor() as cursor:
        cursor.execute(SEED_SQL)
        for name, query in QUERIES.items():
            started = perf_counter()
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
            plan = cursor.fetchone()[0][0]
            wall_ms = (perf_counter() - started) * 1000
            execution_ms = float(plan["Execution Time"])
            if execution_ms > args.assert_max_ms:
                raise SystemExit(f"{name}: {execution_ms:.2f}ms > {args.assert_max_ms:.2f}ms")
            evidence["queries"][name] = {
                "execution_ms": execution_ms,
                "wall_ms": round(wall_ms, 3),
                "plan": plan,
            }
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)
    print(
        json.dumps(
            {name: data["execution_ms"] for name, data in evidence["queries"].items()}, indent=2
        )
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
