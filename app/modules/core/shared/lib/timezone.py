"""Dubai time. The UAE has no daylight saving, so a fixed +04:00 offset is
exact. Stored timestamps are naive UTC (datetime.utcnow)."""
from datetime import datetime, time, timedelta, timezone

DUBAI_TZ = timezone(timedelta(hours=4))


def to_dubai(dt_utc):
    """A naive UTC datetime as an aware Dubai datetime."""
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(DUBAI_TZ)


def local_to_utc(day, at=time.min):
    """`day` at `at` o'clock in Dubai, as naive UTC."""
    local = datetime.combine(day, at, tzinfo=DUBAI_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def local_midnight_utc(day):
    """Midnight at the start of `day` in Dubai, as naive UTC."""
    return local_to_utc(day)


def dubai_today():
    return datetime.now(DUBAI_TZ).date()
