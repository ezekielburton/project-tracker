"""
Weekly and monthly HSE reports: A4 sheets printed from the browser. The
figures are the Statistics view model for the week or month, plus what needs
attention on the day the report is run.
"""

from datetime import date, timedelta

from app.modules.hse.lib.computed import days_to_expiry, effective_status
from app.modules.hse.lib.metrics import compliance_health
from app.modules.hse.lib.overview import entry_title, needs_you_now
from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.schedule import add_months

KINDS = ('week', 'month')

# Rows the incident table holds before "and N more", so the last page still
# fits one A4 sheet.
INCIDENT_ROWS = 12
ATTENTION_ROWS = 4

DATE = '%d %b %Y'


def window(kind, at, today=None):
    """The week (Monday to Sunday) or calendar month holding `at`, and the
    one before it, in the same shape as statistics.period()."""
    today = today or date.today()
    at = min(at or today, today)
    if kind == 'week':
        start = at - timedelta(days=at.weekday())
        end = start + timedelta(days=6)
        prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)
        label = f"Week {start.isocalendar()[1]} · {start.strftime('%d %b')} – {end.strftime(DATE)}"
    else:
        start = at.replace(day=1)
        end = add_months(start, 1) - timedelta(days=1)
        prev_start = add_months(start, -1)
        prev_end = start - timedelta(days=1)
        label = start.strftime('%B %Y')
    return {'view': kind, 'year': None, 'label': label, 'start': start, 'end': end,
            'prev_start': prev_start, 'prev_end': prev_end, 'months': 1}


def navigation(win, today=None):
    """Dates to step to: the day before this period, and the day after it
    unless that is in the future."""
    today = today or date.today()
    after = win['end'] + timedelta(days=1)
    return {'prev': (win['start'] - timedelta(days=1)).isoformat(),
            'next': after.isoformat() if after <= today else None}


def incident_rows(entries, win, limit):
    """Every incident and near miss in the period, oldest first."""
    rows = sorted((e for e in entries if e.register == 'incidents'
                   and e.entry_date and win['start'] <= e.entry_date <= win['end']),
                  key=lambda e: (e.entry_date, e.id or 0))
    out = [{
        'ref': e.ref,
        'date': e.entry_date.strftime('%d %b'),
        'kind': (e.data or {}).get('event_class') or 'Not marked',
        'location': e.location.label if getattr(e, 'location', None) else '—',
        'type': (e.data or {}).get('incident_type') or '—',
        'severity': e.severity or '—',
        'status': effective_status(e, BY_KEY['incidents']) or '—',
    } for e in rows]
    return {'rows': out[:limit], 'total': len(out), 'more': max(0, len(out) - limit)}


def attention(entries, flag_rows, today=None, limit=ATTENTION_ROWS):
    """What needs acting on today: actions over their SLA, service and stock
    flags, and renewals lapsed or expiring within 30 days."""
    today = today or date.today()
    late = [r for r in needs_you_now(entries, today, limit=10 ** 6)['rows'] if r['over_sla']]
    health = compliance_health(entries, today)
    renewals = [{'title': entry_title(e), 'ref': e.ref, 'days': days_to_expiry(e, today)}
                for e in health['lapsed'] + health['expiring']]

    def cut(rows):
        return {'rows': rows[:limit], 'total': len(rows), 'more': max(0, len(rows) - limit)}

    return {
        'late': cut([{'title': r['title'], 'ref': r['ref'], 'label': r['register_label'],
                      'detail': f"{r['over_sla']}d over"} for r in late]),
        'flags': cut([{'title': r['title'], 'ref': r['ref'], 'label': r['register_label'],
                       'detail': r['detail']} for r in flag_rows]),
        'renewals': cut([dict(r, detail=(f"expired {abs(r['days'])}d ago" if r['days'] < 0
                                         else f"{r['days']}d left")) for r in renewals]),
    }
