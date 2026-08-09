from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from clockwork_canary.cron import CronExpression, CronSyntaxError, iter_occurrences


def test_parse_and_match_basic_expression() -> None:
    expression = CronExpression.parse("15 4 * * 1-5")
    assert expression.matches(datetime(2026, 8, 3, 4, 15))
    assert not expression.matches(datetime(2026, 8, 2, 4, 15))
    assert "minutes=15" in expression.describe()


def test_names_lists_and_steps_are_supported() -> None:
    expression = CronExpression.parse("5/20 1,3 * Jan-Mar MON,7")
    assert expression.minutes == frozenset({5, 25, 45})
    assert expression.hours == frozenset({1, 3})
    assert expression.months == frozenset({1, 2, 3})
    assert expression.week_days == frozenset({0, 1})


def test_day_of_month_and_week_use_posix_or_semantics() -> None:
    expression = CronExpression.parse("0 9 1 * MON")
    # Monday even though it is not the first of the month.
    assert expression.matches(datetime(2026, 6, 8, 9, 0))
    # First of month even though it is a Wednesday.
    assert expression.matches(datetime(2026, 7, 1, 9, 0))
    assert not expression.matches(datetime(2026, 7, 2, 9, 0))


@pytest.mark.parametrize(
    "source, message",
    [
        ("* * * *", "exactly 5"),
        ("* * * * * *", "exactly 5"),
        ("60 * * * *", "outside"),
        ("*/0 * * * *", "positive"),
        ("*/x * * * *", "invalid step"),
        ("1//2 * * * *", "invalid step"),
        ("10-2 * * * *", "descending"),
        ("1-2-3 * * * *", "invalid range"),
        (",1 * * * *", "empty item"),
        ("nope * * * *", "invalid minute"),
    ],
)
def test_invalid_expressions_fail_with_repairable_messages(source: str, message: str) -> None:
    with pytest.raises(CronSyntaxError, match=message):
        CronExpression.parse(source)


def test_spring_forward_run_advances_and_keeps_intended_time() -> None:
    expression = CronExpression.parse("30 2 * * *")
    zone = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 7, tzinfo=UTC)
    end = datetime(2026, 3, 10, tzinfo=UTC)
    runs = list(iter_occurrences(expression, zone, start, end))
    adjusted = [item for item in runs if item.adjusted_for_gap]
    assert len(adjusted) == 1
    assert adjusted[0].actual_utc == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    assert adjusted[0].intended_local == datetime(2026, 3, 8, 2, 30)
    assert adjusted[0].local_time.hour == 3


def test_fall_back_yields_both_real_instants() -> None:
    expression = CronExpression.parse("30 1 * * *")
    zone = ZoneInfo("America/New_York")
    start = datetime(2026, 10, 31, tzinfo=UTC)
    end = datetime(2026, 11, 2, 12, tzinfo=UTC)
    runs = list(iter_occurrences(expression, zone, start, end))
    repeated = [item for item in runs if item.local_time.date().isoformat() == "2026-11-01"]
    assert len(repeated) == 2
    assert {item.local_time.fold for item in repeated} == {0, 1}
    assert repeated[0].actual_utc != repeated[1].actual_utc


def test_simulator_requires_aware_ordered_bounds() -> None:
    expression = CronExpression.parse("0 0 * * *")
    zone = ZoneInfo("UTC")
    with pytest.raises(ValueError, match="timezone-aware"):
        list(
            iter_occurrences(
                expression,
                zone,
                datetime(2026, 1, 1),
                datetime(2026, 1, 2),
            )
        )
    start = datetime(2026, 1, 2, tzinfo=UTC)
    assert list(iter_occurrences(expression, zone, start, start)) == []
