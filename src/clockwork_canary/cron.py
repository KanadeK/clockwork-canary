"""A dependency-free parser and simulator for GitHub's five-field cron syntax."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Occurrence


class CronSyntaxError(ValueError):
    """Raised when an expression cannot be interpreted safely."""


_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_WEEKDAY_NAMES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


@dataclass(frozen=True, slots=True)
class CronExpression:
    """Parsed five-field cron expression using POSIX day matching semantics."""

    source: str
    minutes: frozenset[int]
    hours: frozenset[int]
    month_days: frozenset[int]
    months: frozenset[int]
    week_days: frozenset[int]
    month_day_wildcard: bool
    week_day_wildcard: bool

    @classmethod
    def parse(cls, source: str) -> CronExpression:
        fields = source.split()
        if len(fields) != 5:
            raise CronSyntaxError(
                f"expected exactly 5 cron fields, found {len(fields)} in {source!r}"
            )
        minute, hour, month_day, month, week_day = fields
        return cls(
            source=source,
            minutes=_parse_field(minute, 0, 59, "minute"),
            hours=_parse_field(hour, 0, 23, "hour"),
            month_days=_parse_field(month_day, 1, 31, "day of month"),
            months=_parse_field(month, 1, 12, "month", _MONTH_NAMES),
            week_days=_parse_field(week_day, 0, 7, "day of week", _WEEKDAY_NAMES, True),
            month_day_wildcard=month_day == "*",
            week_day_wildcard=week_day == "*",
        )

    def matches(self, value: datetime) -> bool:
        if value.minute not in self.minutes or value.hour not in self.hours:
            return False
        if value.month not in self.months:
            return False

        month_day_matches = value.day in self.month_days
        # Python Monday=0; POSIX Sunday=0.
        week_day = (value.weekday() + 1) % 7
        week_day_matches = week_day in self.week_days

        if self.month_day_wildcard and self.week_day_wildcard:
            day_matches = True
        elif self.month_day_wildcard:
            day_matches = week_day_matches
        elif self.week_day_wildcard:
            day_matches = month_day_matches
        else:
            day_matches = month_day_matches or week_day_matches
        return day_matches

    def describe(self) -> str:
        return (
            f"minutes={_compact(self.minutes)}, hours={_compact(self.hours)}, "
            f"month-days={_compact(self.month_days)}, months={_compact(self.months)}, "
            f"week-days={_compact(self.week_days)}"
        )


def iter_occurrences(
    expression: CronExpression,
    timezone: ZoneInfo,
    start: datetime,
    end: datetime,
) -> Iterator[Occurrence]:
    """Yield runs after ``start`` and through ``end``.

    UTC minutes are the source of truth. During a spring-forward gap, GitHub documents
    that schedules in missing local minutes advance to the next valid local time. Those
    runs are yielded with ``adjusted_for_gap=True`` and their intended wall time retained.
    """

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if end_utc <= start_utc:
        return

    current = start_utc.replace(second=0, microsecond=0)
    if current <= start_utc:
        current += timedelta(minutes=1)
    previous = current - timedelta(minutes=1)
    previous_local_naive = previous.astimezone(timezone).replace(tzinfo=None)

    while current <= end_utc:
        local = current.astimezone(timezone)
        local_naive = local.replace(tzinfo=None)
        wall_delta = local_naive - previous_local_naive

        if wall_delta > timedelta(minutes=1):
            missing = previous_local_naive + timedelta(minutes=1)
            while missing < local_naive:
                if expression.matches(missing):
                    yield Occurrence(
                        actual_utc=current,
                        local_time=local,
                        intended_local=missing,
                        adjusted_for_gap=True,
                    )
                missing += timedelta(minutes=1)

        if expression.matches(local):
            yield Occurrence(actual_utc=current, local_time=local)

        previous_local_naive = local_naive
        current += timedelta(minutes=1)


def _parse_field(
    source: str,
    minimum: int,
    maximum: int,
    label: str,
    names: dict[str, int] | None = None,
    sunday_alias: bool = False,
) -> frozenset[int]:
    if not source:
        raise CronSyntaxError(f"{label} field is empty")
    values: set[int] = set()
    for item in source.split(","):
        if not item:
            raise CronSyntaxError(f"empty item in {label} field {source!r}")
        base, step = _split_step(item, label)
        if base == "*":
            start, stop = minimum, maximum
        elif "-" in base:
            if base.count("-") != 1:
                raise CronSyntaxError(f"invalid range {base!r} in {label} field")
            left, right = base.split("-", 1)
            start = _coerce(left, names, label)
            stop = _coerce(right, names, label)
            if start > stop:
                raise CronSyntaxError(f"descending range {base!r} is not supported")
        else:
            start = _coerce(base, names, label)
            stop = maximum if step != 1 else start

        if start < minimum or stop > maximum:
            raise CronSyntaxError(
                f"{label} value {base!r} is outside the supported {minimum}-{maximum} range"
            )
        values.update(range(start, stop + 1, step))

    if sunday_alias and 7 in values:
        values.remove(7)
        values.add(0)
    if not values:
        raise CronSyntaxError(f"{label} field {source!r} selects no values")
    return frozenset(values)


def _split_step(item: str, label: str) -> tuple[str, int]:
    if "/" not in item:
        return item, 1
    if item.count("/") != 1:
        raise CronSyntaxError(f"invalid step {item!r} in {label} field")
    base, raw_step = item.split("/", 1)
    try:
        step = int(raw_step)
    except ValueError as exc:
        raise CronSyntaxError(f"invalid step {raw_step!r} in {label} field") from exc
    if step <= 0:
        raise CronSyntaxError(f"step must be positive in {label} field")
    return base, step


def _coerce(source: str, names: dict[str, int] | None, label: str) -> int:
    lowered = source.lower()
    if names and lowered in names:
        return names[lowered]
    try:
        return int(source)
    except ValueError as exc:
        raise CronSyntaxError(f"invalid {label} value {source!r}") from exc


def _compact(values: frozenset[int]) -> str:
    return ",".join(str(item) for item in sorted(values))
