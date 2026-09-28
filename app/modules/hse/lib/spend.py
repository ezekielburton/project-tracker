"""
Spend view models (the Overview's Spend panel and the cost-register strip)
and money formatting. Figures come from lib/metrics.py over
query.spend_entries(), so both surfaces count the same rows.
"""

from datetime import date
from decimal import Decimal

from app.modules.hse.lib.metrics import (
    parse_money, spend_by_area, spend_by_month, spend_summary,
)
from app.modules.hse.lib.rail import GROUP_LABELS

MONTH_LABELS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def aed(amount, unit=True):
    """'AED 12,450'; fils only when there are any ('AED 12,450.50')."""
    amount = Decimal(amount).quantize(Decimal('0.01'))
    places = 0 if amount == amount.to_integral_value() else 2
    text = f'{amount:,.{places}f}'
    return f'AED {text}' if unit else text


def amount_text(value):
    """A stored money value for display, no unit: '1,850', '2,400.50'. Text
    that is not an amount (legacy entries) shows as stored."""
    amount = parse_money(value)
    return aed(amount, unit=False) if amount is not None else value


def stored_amount(amount):
    """How a money field is saved: a plain number, fils only when non-zero
    ('1250', '1250.50'). parse_money reads it back unchanged."""
    return aed(amount, unit=False).replace(',', '')


def _figures(summary, today):
    return [
        {'label': 'This month', 'value': aed(summary['month']),
         'sub': today.strftime('%B')},
        {'label': 'This year', 'value': aed(summary['year']), 'sub': str(today.year)},
        {'label': 'All time', 'value': aed(summary['all_time']), 'sub': 'Every entry'},
    ]


def spend_panel(entries, today=None):
    """The Overview panel: three figures, then this year's spend by area.
    An area with more than one cost register lists its registers under it."""
    today = today or date.today()
    split = spend_by_area(entries, date(today.year, 1, 1), date(today.year, 12, 31))
    areas = [{
        'label': GROUP_LABELS.get(area['group'], area['group'].title()),
        'amount': aed(area['amount']),
        'share': area['share'],
        'registers': [{'label': r['label'], 'amount': aed(r['amount']),
                       'share': r['share']}
                      for r in area['registers']] if len(area['registers']) > 1 else [],
    } for area in split['areas']]
    return {
        'figures': _figures(spend_summary(entries, today), today),
        'areas': areas,
        'year': today.year,
        'total': aed(split['total']),
    }


def spend_strip(entries, year, today=None):
    """A cost register's strip: three figures and `year` month by month. A
    month with no spend has value None."""
    today = today or date.today()
    by_month = spend_by_month(entries, year)
    return {
        'figures': _figures(spend_summary(entries, today), today),
        'year': year,
        'months': [{'label': label, 'value': aed(amount, unit=False) if amount else None}
                   for label, amount in zip(MONTH_LABELS, by_month['months'])],
        'total': aed(by_month['total']),
    }
