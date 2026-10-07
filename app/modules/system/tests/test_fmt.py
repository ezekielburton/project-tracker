"""Labels: durations and past Dubai times."""
from datetime import datetime

from app.modules.system.lib import fmt

NOW = datetime(2026, 10, 7, 10, 0)  # 14:00 Dubai, a Wednesday


def test_durations():
    assert fmt.ms(None) is None
    assert fmt.ms(640) == '640 ms'
    assert fmt.ms(1820) == '1.82 s'
    assert fmt.ms(75_400) == '75.4 s'
    assert fmt.ms(506_000) == '506 s'


def test_past_times():
    assert fmt.day_time(None, NOW) is None
    assert fmt.day_time(datetime(2026, 10, 7, 6, 12), NOW) == 'today 10:12'
    assert fmt.day_time(datetime(2026, 10, 6, 12, 40), NOW) == 'yesterday 16:40'
    assert fmt.day_time(datetime(2026, 10, 5, 5, 3), NOW) == 'Mon 09:03'
    assert fmt.day_time(datetime(2026, 9, 12, 5, 3), NOW) == '12 Sep 09:03'
