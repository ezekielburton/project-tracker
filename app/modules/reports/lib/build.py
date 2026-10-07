"""Builds every report for a period from one load, with change against the
previous period. The PDF and email templates render what this returns."""
from numbers import Number

from app.modules.reports.lib import facts as facts_lib
from app.modules.reports.lib.metrics import company, department
from app.modules.reports.lib.people import DEPARTMENT_REPORTS, everyone

# Counts that get a change arrow, per department report.
_DELTA_KEYS = ('worked', 'closed', 'invoiced', 'aed', 'hit', 'missed', 'approvals',
               'incomplete', 'uploaded', 'score')
_PERSON_DELTA_KEYS = ('worked', 'closed', 'invoiced', 'hit', 'approvals', 'uploaded', 'score')

# Periods in the consolidated report's score chart, this one included.
TREND_LENGTH = 6


def _all(period, by_report, today):
    """(department data by report, company totals) from one load."""
    ids = {u.id for people in by_report.values() for u in people}
    f = facts_lib.load(period, ids, today)
    depts = {report: department(f, report, by_report[report]) for report in DEPARTMENT_REPORTS}
    return depts, company(f, by_report)


def _company_score(depts):
    """Department scores weighted by headcount."""
    people = sum(d['people'] for d in depts.values())
    return round(sum(d['score'] * d['people'] for d in depts.values()) / people) if people else 0


def _number(value):
    return isinstance(value, Number) and not isinstance(value, bool)


def _delta(now, before, keys):
    return {k: now[k] - before[k] for k in keys if _number(now.get(k)) and _number(before.get(k))}


def _longest_waits(depts, n=2):
    """Longest waits to invoice across CS and Project Owners, each project once."""
    rows = {r['project_id']: r for key in ('client_servicing', 'project_owner')
            for r in depts[key]['waiting_invoice']}
    return sorted(rows.values(), key=lambda r: -r['days'])[:n]


def _consolidated(depts, previous, totals, trend):
    score = _company_score(depts)
    rows = [r | {'report': key} for key, d in depts.items() for r in d['rows']]
    return {
        'report': 'consolidated', 'people': sum(d['people'] for d in depts.values()), 'score': score,
        'delta': {'score': score - _company_score(previous)}, 'company': totals, 'trend': trend,
        'no_activity': [(r['user'], r['report']) for r in rows if r['no_activity']],
        'lowest': sorted((r for r in rows if not r['no_activity']), key=lambda r: r['score'])[:2],
        'most_missed': sorted((r for r in rows if r.get('missed')), key=lambda r: -r['missed'])[:2],
        'waiting_invoice': _longest_waits(depts),
    }


def _trend(period, by_report, today, now, before):
    """Company score for the last TREND_LENGTH periods, oldest first."""
    periods = [period.previous(), period]
    while len(periods) < TREND_LENGTH:
        periods.insert(0, periods[0].previous())
    scores = [_company_score(_all(p, by_report, today)[0]) for p in periods[:-2]]
    scores += [_company_score(before), _company_score(now)]
    return [{'label': p.tick_label, 'score': s} for p, s in zip(periods, scores)]


def build(period, today=None):
    """{'client_servicing': ..., 'project_owner': ..., 'design': ..., 'consolidated': ...}"""
    by_report = everyone()
    now, totals = _all(period, by_report, today)
    before, _ = _all(period.previous(), by_report, today)
    trend = _trend(period, by_report, today, now, before)
    for report, data in now.items():
        prev = before[report]
        data['delta'] = _delta(data, prev, _DELTA_KEYS)
        prev_rows = {r['user'].id: r for r in prev['rows']}
        for row in data['rows']:
            row['delta'] = _delta(row, prev_rows.get(row['user'].id, {}), _PERSON_DELTA_KEYS)
        data['period'] = period
    out = dict(now)
    out['consolidated'] = _consolidated(now, before, totals, trend) | {'period': period}
    return out
