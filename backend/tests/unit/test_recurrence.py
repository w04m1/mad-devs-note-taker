# ruff: noqa: DTZ001
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.recurrence import expand_occurrences


def test_daily_and_weekly_end_date_is_inclusive() -> None:
    daily = expand_occurrences(datetime(2025, 1, 1, 9), "UTC", "daily", date(2025, 1, 3))
    assert [x.local.date() for x in daily] == [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
    weekly = expand_occurrences(datetime(2025, 1, 1, 9), "UTC", "weekly", date(2025, 1, 15))
    assert [x.local.date() for x in weekly] == [
        date(2025, 1, 1),
        date(2025, 1, 8),
        date(2025, 1, 15),
    ]


def test_monthly_invalid_dates_are_skipped_not_clamped() -> None:
    values = expand_occurrences(datetime(2025, 1, 31, 9), "UTC", "monthly", date(2025, 5, 31))
    assert [x.local.date() for x in values] == [
        date(2025, 1, 31),
        date(2025, 3, 31),
        date(2025, 5, 31),
    ]


def test_dst_gap_is_skipped_and_overlap_uses_earlier_instant() -> None:
    gap = expand_occurrences(
        datetime(2025, 3, 29, 2, 30), "Europe/Budapest", "daily", date(2025, 3, 31)
    )
    assert [x.local.date() for x in gap] == [date(2025, 3, 29), date(2025, 3, 31)]
    overlap = expand_occurrences(
        datetime(2025, 10, 26, 2, 30), "Europe/Budapest", "daily", date(2025, 10, 26)
    )
    assert overlap[0].instant == datetime(2025, 10, 26, 0, 30, tzinfo=UTC)


def test_limit_accepts_exactly_limit_and_rejects_one_more() -> None:
    start = datetime(2000, 1, 1, 12)
    assert (
        len(expand_occurrences(start, "UTC", "daily", start.date() + timedelta(days=9_999)))
        == 10_000
    )
    with pytest.raises(OverflowError, match="10000"):
        expand_occurrences(start, "UTC", "daily", start.date() + timedelta(days=10_000))


@pytest.mark.parametrize("zone", ["Mars/Olympus", ""])
def test_invalid_timezone(zone: str) -> None:
    with pytest.raises(ValueError, match="unknown IANA"):
        expand_occurrences(datetime(2025, 1, 1), zone, "daily", date(2025, 1, 2))


def test_end_before_start_is_invalid() -> None:
    with pytest.raises(ValueError, match="end_date"):
        expand_occurrences(datetime(2025, 1, 2), "UTC", "daily", date(2025, 1, 1))
