#!/usr/bin/env python3
"""Measure maximum-size synchronous recurrence creation with rollback and read probes."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select, text

from app.api.schemas import SeriesCreate
from app.db.models import Note, ReminderDelivery, ReminderRule
from app.db.session import async_session_factory
from app.domain.recurrence import create_series_rows


async def one_run(offsets: list[int]) -> dict[str, float | int]:
    first = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    payload = SeriesCreate(
        title="10k materialization benchmark",
        body="",
        starts_at=first,
        active=True,
        tag_ids=[],
        reminder_offsets_minutes=offsets,
        local_start=first.replace(tzinfo=None),
        timezone="UTC",
        frequency="daily",
        end_date=first.date() + timedelta(days=9_999),
    )
    stop = asyncio.Event()
    reader_ready = asyncio.Event()
    read_latencies: list[float] = []

    async def read_probe() -> None:
        async with async_session_factory() as reader:
            await reader.execute(text("SELECT 1"))
            reader_ready.set()
            while not stop.is_set():
                started = perf_counter()
                await reader.execute(text("SELECT 1"))
                read_latencies.append(perf_counter() - started)
                await asyncio.sleep(0.02)

    probe = asyncio.create_task(read_probe())
    await reader_ready.wait()
    started = perf_counter()
    async with async_session_factory() as session:
        transaction = await session.begin()
        series = await create_series_rows(session, payload, datetime.now(UTC), limit=10_000)
        elapsed = perf_counter() - started
        notes = await session.scalar(
            select(func.count()).select_from(Note).where(Note.series_id == series.id)
        )
        rules = await session.scalar(
            select(func.count())
            .select_from(ReminderRule)
            .join(Note, Note.id == ReminderRule.note_id)
            .where(Note.series_id == series.id)
        )
        deliveries = await session.scalar(
            select(func.count())
            .select_from(ReminderDelivery)
            .join(ReminderRule, ReminderRule.id == ReminderDelivery.reminder_rule_id)
            .join(Note, Note.id == ReminderRule.note_id)
            .where(Note.series_id == series.id)
        )
        await transaction.rollback()
    stop.set()
    await probe
    async with async_session_factory() as session:
        rolled_back = await session.scalar(
            select(func.count()).select_from(Note).where(Note.series_id == series.id)
        )
    return {
        "seconds": round(elapsed, 3),
        "notes": notes or 0,
        "rules": rules or 0,
        "deliveries": deliveries or 0,
        "rolled_back_notes": rolled_back or 0,
        "read_probe_count": len(read_latencies),
        "p95_read_seconds": round(
            statistics.quantiles(read_latencies, n=20)[18] if len(read_latencies) >= 20 else 0,
            3,
        ),
        "max_read_seconds": round(max(read_latencies, default=0), 3),
    }


async def benchmark(runs: int) -> dict[str, object]:
    cases = {}
    for name, offsets, median_gate in (
        ("zero_offsets", [], 10.0),
        ("three_offsets", [10, 60, 1440], 45.0),
    ):
        results = [await one_run(offsets) for _ in range(runs)]
        median = statistics.median(float(item["seconds"]) for item in results)
        valid = all(
            item["notes"] == 10_000
            and item["rules"] == 10_000 * len(offsets)
            and item["deliveries"] == 10_000 * len(offsets)
            and item["rolled_back_notes"] == 0
            and item["max_read_seconds"] <= 2.0
            for item in results
        )
        cases[name] = {
            "offsets": offsets,
            "runs": results,
            "median_seconds": round(median, 3),
            "median_gate_seconds": median_gate,
            "passed": valid and median <= median_gate,
        }
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "runs_per_case": runs,
        "cases": cases,
        "passed": all(case["passed"] for case in cases.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs must be at least 3 for the distribution gate")
    result = asyncio.run(benchmark(args.runs))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
