"""Builds every report for a period from one load, with change against the
previous period. The PDF and email templates render what this returns."""
from numbers import Number

from app.modules.reports.lib import facts as facts_lib
from app.modules.reports.lib.metrics import department
from app.modules.reports.lib.people import DEPARTMENT_REPORTS, everyone

# Counts that get a change arrow, per department report.
_DELTA_KEYS = ('worked', 'closed', 'invoiced', 'aed', 'hit', 'missed', 'approvals',
               'incomplete', 'uploaded', 'score')
_PERSON_DELTA_KEYS = ('worked', 'closed', 'invoiced', 'hit', 'approvals', 'uploaded', 'score')


def _all(period, by_report, today):
    ids = {u.id for people in by_report.values() for u in people}
    f = facts_lib.load(period, ids, today)
    return {report: department(f, report, by_report[report]) for report in DEPARTMENT_REPORTS}


def _number(value):
    return isinstance(value, Number) and not isinstance(value, bool)


def _delta(now, before, keys):
    return {k: now[k] - before[k] for k in keys if _number(now.get(k)) and _number(before.get(k))}


def _longest_waits(depts, n=2):
    """Longest waits to invoice across CS and Project Owners, each project once."""
    rows = {r['project_id']: r for key in ('client_servicing', 'project_owner')
            for r in depts[key]['waiting_invoice']}
    return sorted(rows.values(), key=lambda r: -r['days'])[:n]


def _consolidated(depts, previous):
    people = sum(d['people'] for d in depts.values())
    company = round(sum(d['score'] * d['people'] for d in depts.values()) / people) if people else 0
    prev_people = sum(d['people'] for d in previous.values())
    prev_company = (round(sum(d['score'] * d['people'] for d in previous.values()) / prev_people)
                    if prev_people else 0)
    rows = [r | {'report': key} for key, d in depts.items() for r in d['rows']]
    return {
        'report': 'consolidated', 'people': people, 'score': company,
        'delta': {'score': company - prev_company}, 'departments': depts,
        'no_activity': [(r['user'], r['report']) for r in rows if r['no_activity']],
        'lowest': sorted((r for r in rows if not r['no_activity']), key=lambda r: r['score'])[:2],
        'most_missed': sorted((r for r in rows if r.get('missed')), key=lambda r: -r['missed'])[:2],
        'waiting_invoice': _longest_waits(depts),
    }


def build(period, today=None):
    """{'client_servicing': ..., 'project_owner': ..., 'design': ..., 'consolidated': ...}"""
    by_report = everyone()
    now = _all(period, by_report, today)
    before = _all(period.previous(), by_report, today)
    for report, data in now.items():
        prev = before[report]
        data['delta'] = _delta(data, prev, _DELTA_KEYS)
        prev_rows = {r['user'].id: r for r in prev['rows']}
        for row in data['rows']:
            row['delta'] = _delta(row, prev_rows.get(row['user'].id, {}), _PERSON_DELTA_KEYS)
        data['period'] = period
    out = dict(now)
    out['consolidated'] = _consolidated(now, before) | {'period': period}
    return out
