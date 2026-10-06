"""Report periods: a Mon-Fri week or a calendar month, in Dubai time. Stored
times are naive UTC, so utc_bounds() converts the edges."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, time, timedelta

from app.modules.core.shared.lib.timezone import local_midnight_utc, local_to_utc

WEEKLY = 'weekly'
MONTHLY = 'monthly'

# Scheduled sends: 08:00 Dubai, Monday for weekly, the 1st for monthly.
SEND_TIME = time(8)


def _day(d):
    """'Mon 29 Sep'. Built by hand: %-d doesn't exist on Windows."""
    return f'{d:%a} {d.day} {d:%b}'


@dataclass(frozen=True)
class Period:
    kind: str
    start: date  # the Monday, or the 1st
    end: date    # the Friday, or the last day (inclusive)

    @classmethod
    def week_of(cls, day):
        monday = day - timedelta(days=day.weekday())
        return cls(WEEKLY, monday, monday + timedelta(days=4))

    @classmethod
    def month_of(cls, day):
        first = day.replace(day=1)
        return cls(MONTHLY, first, first.replace(day=monthrange(first.year, first.month)[1]))

    @classmethod
    def of(cls, kind, day):
        return cls.week_of(day) if kind == WEEKLY else cls.month_of(day)

    @classmethod
    def last_complete(cls, kind, today):
        """What a scheduled run reports on: last week, or last month."""
        if kind == WEEKLY:
            return cls.week_of(today - timedelta(days=today.weekday() + 7))
        return cls.month_of(today.replace(day=1) - timedelta(days=1))

    def previous(self):
        if self.kind == WEEKLY:
            return Period.week_of(self.start - timedelta(days=7))
        return Period.month_of(self.start - timedelta(days=1))

    def utc_bounds(self):
        """[start, end) as naive UTC, for filtering stored timestamps."""
        return local_midnight_utc(self.start), local_midnight_utc(self.end + timedelta(days=1))

    def working_days(self):
        """The Mon-Fri dates in the period. Public holidays aren't modelled."""
        days = (self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1))
        return [d for d in days if d.weekday() < 5]

    def contains(self, day):
        return self.start <= day <= self.end

    def scheduled_send_at(self):
        """When the scheduled run sends this period, as naive UTC."""
        day = self.start + timedelta(days=7) if self.kind == WEEKLY else self.end + timedelta(days=1)
        return local_to_utc(day, SEND_TIME)

    @property
    def week_number(self):
        return self.start.isocalendar()[1]

    @property
    def label(self):
        """'Week 40 · Mon 28 Sep – Fri 2 Oct 2026' or 'September 2026 · 22 working days'."""
        if self.kind == WEEKLY:
            return f'Week {self.week_number} · {_day(self.start)} – {_day(self.end)} {self.end.year}'
        return f'{self.start:%B %Y} · {len(self.working_days())} working days'

    @property
    def short_label(self):
        """'Wk 40 · 28 Sep – 2 Oct' or 'September 2026'."""
        if self.kind == WEEKLY:
            return f'Wk {self.week_number} · {self.start.day} {self.start:%b} – {self.end.day} {self.end:%b}'
        return f'{self.start:%B %Y}'

    @property
    def file_stem(self):
        """'Wk40' or '2026-09', for PDF file names."""
        return f'Wk{self.week_number}' if self.kind == WEEKLY else f'{self.start:%Y-%m}'
