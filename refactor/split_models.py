"""One-shot: split app/models/__init__.py into a domain package under
app/modules/core/shared/models/, leaving a re-export shim behind.
Reads the ORIGINAL file, guards against double-runs, and self-verifies."""
import os

SRC = os.path.join('app', 'models', '__init__.py')
PKG = os.path.join('app', 'modules', 'core', 'shared', 'models')

# class/def/const name -> destination file (no .py)
MAPPING = {
    'load_user': 'users', 'DEFAULT_ROLE_TITLES': 'users', 'User': 'users',
    'RoleTitle': 'users', 'UserTableLayout': 'users', 'ProjectTableView': 'users',
    'Client': 'clients', 'Customer': 'clients', 'Contact': 'clients',
    'Scope': 'projects', 'Project': 'projects', 'ProjectDesigner': 'projects',
    'ProjectReviewer': 'projects', 'ProjectApproval': 'projects', 'ProjectRegion': 'projects',
    'ProjectCustomer': 'projects', 'ProjectSecondaryCS': 'projects',
    'ProjectSecondaryCsRegion': 'projects', 'ProjectPosmChannel': 'projects',
    'ProjectOverlaySeen': 'projects', 'ProjectFile': 'projects', 'SiteVisit': 'projects',
    'DesignType': 'projects', 'DesignDirection': 'projects',
    'DeliverableType': 'deliverables', 'DeliverableTypeDiscipline': 'deliverables',
    'Deliverable': 'deliverables', 'DeliverableAssignment': 'deliverables',
    'DeliverablePreproductionEvent': 'deliverables',
    'ProjectStatusLog': 'status_logs', 'ProjectCustomerStatusLog': 'status_logs',
    'DeliverableStatusLog': 'status_logs',
    'ProjectSubmission': 'submissions', 'ProjectSubmissionDeliverable': 'submissions',
    'ProjectSubmissionEvent': 'submissions', 'ProjectSubmissionEventDeliverable': 'submissions',
    'ProjectSubmissionFile': 'submissions', 'ProjectRevision': 'submissions',
    'ProjectRevisionDeliverable': 'submissions', 'TechnicalSubmission': 'submissions',
    'BriefFlag': 'flags', 'BriefFlagMessage': 'flags', 'DecisionFlag': 'flags',
    'DecisionFlagMessage': 'flags',
    'ProjectNote': 'notes', 'ProjectNoteReaction': 'notes',
    'Notification': 'notifications', 'NotificationSound': 'notifications',
    'ActivityLog': 'activity', 'SidebarClick': 'activity',
    'BlogPost': 'blog', '_BlogSection': 'blog', '_BlogBlock': 'blog', 'BlogComment': 'blog',
    'FeatureRequest': 'feedback', 'FeatureRequestUpvote': 'feedback',
    'FeatureRequestComment': 'feedback', 'BugReport': 'feedback', 'BugReportComment': 'feedback',
    'WikiSection': 'wiki', 'WikiArticle': 'wiki',
    'AchievementCategory': 'achievements', 'AchievementBorder': 'achievements',
    'Achievement': 'achievements', 'UserAchievement': 'achievements',
    'UserDisplaySettings': 'achievements', 'UserPinnedAchievement': 'achievements',
}
FILE_ORDER = ['users', 'clients', 'projects', 'deliverables', 'status_logs',
              'submissions', 'flags', 'notes', 'notifications', 'activity',
              'blog', 'feedback', 'wiki', 'achievements']

HEADER_USERS = ("from app.modules.core.shared.extensions import db, login_manager\n"
                "from flask_login import UserMixin\n"
                "from datetime import datetime\n")
HEADER_DEFAULT = ("from app.modules.core.shared.extensions import db\n"
                  "from datetime import datetime\n")

src = open(SRC, encoding='utf-8').read()
assert 'class User(db.Model' in src, 'SRC is not the original models file — aborting (already split?).'
lines = src.split('\n')

# locate top-level segments (class / def / UPPER_CONST), backing up over decorators
starts = []
for i, l in enumerate(lines):
    if l.startswith('class '):
        starts.append((l[6:].split('(')[0].split(':')[0].strip(), i))
    elif l.startswith('def '):
        starts.append((l[4:].split('(')[0].strip(), i))
    elif l[:1].isalpha() and l[:1].isupper() and ' = ' in l and l.split(' = ', 1)[0].isidentifier():
        starts.append((l.split(' = ', 1)[0], i))

def back_over_decorators(idx):
    while idx - 1 >= 0 and lines[idx - 1].lstrip().startswith('@'):
        idx -= 1
    return idx

segs = []
for k, (name, idx) in enumerate(starts):
    s = back_over_decorators(idx)
    e = (back_over_decorators(starts[k + 1][1]) - 1) if k + 1 < len(starts) else len(lines) - 1
    segs.append((name, s, e))

unmapped = [n for n, _, _ in segs if n not in MAPPING]
assert not unmapped, f'Unmapped segments (fix MAPPING): {unmapped}'

# bucket exact source text per destination file, preserving original order
buckets = {f: [] for f in FILE_ORDER}
for name, s, e in segs:
    buckets[MAPPING[name]].append((s, '\n'.join(lines[s:e + 1]).rstrip()))

os.makedirs(PKG, exist_ok=True)
LAZY = ('        from app.modules.core.shared.models.flags import DecisionFlag\n'
        '        return DecisionFlag.query.filter_by(')
for f in FILE_ORDER:
    body = '\n\n\n'.join(text for _, text in sorted(buckets[f], key=lambda x: x[0]))
    if f == 'projects':
        needle = '        return DecisionFlag.query.filter_by('
        assert body.count(needle) == 1, 'active_decision_flag needle not unique'
        body = body.replace(needle, LAZY, 1)
    header = HEADER_USERS if f == 'users' else HEADER_DEFAULT
    open(os.path.join(PKG, f + '.py'), 'w', encoding='utf-8').write(header + '\n\n' + body + '\n')

# package __init__ re-exports every public name
public = {f: [n for n, _, _ in segs if MAPPING[n] == f and not n.startswith('_')] for f in FILE_ORDER}
init = ['"""Domain-split SQLAlchemy models. Every model shares the one db registry\n'
        'from core/shared/extensions, so cross-file relationships resolve normally.\n'
        'This package re-exports every model as the single import surface."""']
allnames = []
for f in FILE_ORDER:
    init.append(f'from .{f} import ' + ', '.join(public[f]))
    allnames += public[f]
init.append('')
init.append('__all__ = [\n    ' + ',\n    '.join(repr(n) for n in allnames) + ',\n]')
open(os.path.join(PKG, '__init__.py'), 'w', encoding='utf-8').write('\n'.join(init) + '\n')

# replace the old models module with a compatibility shim (done LAST)
open(SRC, 'w', encoding='utf-8').write(
    '"""Compatibility shim. The models now live in\n'
    'app/modules/core/shared/models/ as a domain-split package. Every model is\n'
    're-exported here so existing `from app.models import X` imports keep working\n'
    'while feature modules migrate to importing from core/shared directly."""\n'
    'from app.modules.core.shared.extensions import db, login_manager  # noqa: F401\n'
    'from app.modules.core.shared.models import *  # noqa: F401,F403\n')

print('Split OK:', sum(len(v) for v in buckets.values()), 'segments across', len(FILE_ORDER), 'files')
for f in FILE_ORDER:
    print(f'  {f:14s} {len(public[f])} public name(s)')