"""Parsing free-text invoice months (pasted values and the data migration),
plus display and input formatting."""
from datetime import date

import pytest

from app.modules.client_servicing.lib.months import (
    format_month, month_input_value, parse_month,
)


@pytest.mark.parametrize('text,expected', [
    ('2026-08', date(2026, 8, 1)),      # what the month picker sends
    ('Aug 2026', date(2026, 8, 1)),
    ('August 2026', date(2026, 8, 1)),
    ('aug 2026', date(2026, 8, 1)),
    ('Sept 2026', date(2026, 9, 1)),
    ('08/2026', date(2026, 8, 1)),
    ('8/2026', date(2026, 8, 1)),
    ('Aug-26', date(2026, 8, 1)),
    ('Dec-2025', date(2025, 12, 1)),
    ('2026/12', date(2026, 12, 1)),
])
def test_a_written_month_reads_as_the_first_of_it(text, expected):
    assert parse_month(text) == expected


@pytest.mark.parametrize('text', ['', None, 'sometime', 'Q3', 'next month', '2026'])
def test_what_cannot_be_read_is_none(text):
    """Unreadable text returns None, never a guessed month."""
    assert parse_month(text) is None


def test_display_and_input_shapes():
    assert format_month(date(2026, 8, 1)) == 'Aug 2026'
    assert month_input_value(date(2026, 8, 1)) == '2026-08'
    assert format_month(None) is None
    assert month_input_value(None) == ''
