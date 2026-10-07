"""Turns the loaded Facts into report data: one row per person, department
totals, the adoption score and the short lists. Reads Facts only, so every
report built from one load agrees."""
from app.modules.reports.lib.people import is_lead
from app.modules.reports.lib.score import LABELS, percent, pooled, score

# Length of each short list on the PDF.
LIST_SIZE = 5


def _credited(rows, uid):
    return [r for r in rows if uid in r['people']]


def person_row(f, user, report):
    """Counts and score for one person."""
    uid = user.id
    worked = f.worked.get(uid, set())
    row = {'user': user, 'worked': len(worked), 'active': len(f.active_days.get(uid, ())),
           'lead': report == 'design' and is_lead(user)}
    if report == 'design':
        due = [d for d in f.design_deadlines if uid in d['designers']]
        hit = sum(1 for d in due if d['hit'])
        delivered = f.delivered.get(uid, set())
        rounds = sum(f.revisions.get(pid, 0) for pid in worked)
        row.update(uploaded=f.file_uploads[uid] + f.stream_uploads[uid], hit=hit, missed=len(due) - hit,
                   revisions=round(rounds / len(worked), 1) if worked else None)
        row['components'] = [('deadlines', hit, len(due)),
                             ('uploaded', len(delivered & f.with_upload), len(delivered)),
                             ('active', row['active'], f.working_days)]
    else:
        installs = _credited(f.cs['installs'], uid)
        jobs = _credited(f.cs['jobs'], uid)
        invoiced = _credited(f.cs['invoiced'], uid)
        hit = sum(1 for r in installs if r['done'])
        incomplete = sum(1 for r in jobs if r['missing'])
        row.update(closed=len(_credited(f.cs['closed'], uid)), invoiced=len(invoiced),
                   aed=sum(r['amount'] for r in invoiced), hit=hit, missed=len(installs) - hit,
                   approvals=f.approvals[uid], incomplete=incomplete)
        row['components'] = [('complete', len(jobs) - incomplete, len(jobs)),
                             ('deadlines', hit, len(installs)),
                             ('approvals', f.approvals[uid], f.approvals[uid] + f.waiting_approval[uid]),
                             ('active', row['active'], f.working_days)]
    row['score'] = score(row['components'])
    row['no_activity'] = row['worked'] == 0 and row['active'] == 0
    return row


def _unique(rows, uids):
    """Rows credited to anyone in the department, each project once."""
    return {r['project_id']: r for r in rows if uids & set(r['people'])}.values()


def department(f, report, people):
    """Report data for one department."""
    rows = [person_row(f, u, report) for u in people]
    uids = {u.id for u in people}
    components = pooled(r['components'] for r in rows)
    data = {
        'report': report, 'rows': rows, 'people': len(rows), 'working_days': f.working_days,
        'components': [{'key': k, 'label': LABELS[k], 'percent': percent(d, t) or 0}
                       for k, d, t in components],
        'score': score(components),
        'no_activity': [r['user'] for r in rows if r['no_activity']],
        'worked': len(set().union(*(f.worked.get(uid, set()) for uid in uids))) if uids else 0,
    }
    if report == 'design':
        due = [d for d in f.design_deadlines if uids & d['designers']]
        hit = sum(1 for d in due if d['hit'])
        worked = set().union(*(f.worked.get(uid, set()) for uid in uids)) if uids else set()
        rounds = sum(f.revisions.get(pid, 0) for pid in worked)
        data.update(
            uploaded=sum(r['uploaded'] for r in rows), hit=hit, missed=len(due) - hit,
            revisions=round(rounds / len(worked), 1) if worked else None,
            missed_list=[d for d in due if not d['hit']][:LIST_SIZE],
            most_revised=sorted(({'name': f.project_names[pid], 'rounds': f.revisions[pid]}
                                 for pid in worked if f.revisions.get(pid)),
                                key=lambda r: -r['rounds'])[:3],
        )
    else:
        installs = list(_unique(f.cs['installs'], uids))
        invoiced = list(_unique(f.cs['invoiced'], uids))
        hit = sum(1 for r in installs if r['done'])
        incomplete = [r for r in _unique(f.cs['jobs'], uids) if r['missing']]
        data.update(
            closed=len(list(_unique(f.cs['closed'], uids))), invoiced=len(invoiced),
            aed=sum(r['amount'] for r in invoiced), hit=hit, missed=len(installs) - hit,
            approvals=sum(r['approvals'] for r in rows), incomplete=len(incomplete),
            waiting_invoice=[r for r in f.cs['waiting_invoice'] if uids & set(r['people'])][:LIST_SIZE],
            incomplete_list=incomplete[:LIST_SIZE],
        )
    return data


def company(f, by_report):
    """Company totals for the consolidated report, each project or
    deliverable counted once across departments."""
    cs_ids = {u.id for key in ('client_servicing', 'project_owner') for u in by_report[key]}
    all_ids = cs_ids | {u.id for u in by_report['design']}
    installs = list(_unique(f.cs['installs'], cs_ids))
    invoiced = list(_unique(f.cs['invoiced'], cs_ids))
    due = [d for d in f.design_deadlines if all_ids & d['designers']]
    hit = sum(1 for r in installs if r['done']) + sum(1 for d in due if d['hit'])
    return {
        'worked': len(set().union(*(f.worked.get(uid, set()) for uid in all_ids))),
        'closed': len(list(_unique(f.cs['closed'], cs_ids))),
        'invoiced': len(invoiced), 'aed': sum(r['amount'] for r in invoiced),
        'hit': hit, 'missed': len(installs) + len(due) - hit,
        'approvals': sum(f.approvals[uid] for uid in cs_ids),
        'incomplete': sum(1 for r in _unique(f.cs['jobs'], cs_ids) if r['missing']),
    }
