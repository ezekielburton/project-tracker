"""
The help-key registry: every place in the app that should have a wiki article.

A page declares a key, an article claims it, and the editor's Coverage panel
lists the keys nothing has claimed yet. A test checks that no template uses a
key that is missing from here.
"""

HELP_KEY_GROUPS = [
    ('Getting started', [
        ('core.overview', 'What OVP is for'),
        ('core.navigation', 'Finding your way around'),
        ('core.roles', 'Who does what'),
        ('core.profile', 'Your profile and settings'),
    ]),
    ('Dashboard', [
        ('dashboard.overview', 'Reading your dashboard'),
        ('dashboard.cards', 'What each card means'),
    ]),
    ('Projects', [
        ('projects.table', 'Reading the projects table'),
        ('projects.filters', 'Filtering and sorting'),
        ('projects.create', 'Starting a project'),
        ('projects.details', 'The Details tab'),
        ('projects.deliverables', 'The Deliverables tab'),
        ('projects.submissions', 'Submitting a draft for review'),
        ('projects.preproduction', 'Pre-production'),
        ('projects.flags', 'Raising a flag'),
        ('projects.notes', 'Notes and chat'),
    ]),
    ('Client Servicing', [
        ('cs.table', 'The CS table, column by column'),
        ('cs.dashboard', 'The CS dashboard'),
        ('cs.calendar', 'The CS calendar'),
        ('cs.invoicing', 'The invoicing tab'),
        ('cs.closed', 'Closed projects'),
    ]),
    ('Digital Innovation', [
        ('di.board', 'The DI board'),
        ('di.templates', 'DI templates'),
        ('di.performance', 'DI performance'),
        ('di.archive', 'The DI archive'),
    ]),
    ('HSE', [
        ('hse.overview', 'HSE overview'),
        ('hse.registers', 'Registers'),
        ('hse.schedule', 'Scheduling inspections'),
        ('hse.calendar', 'The HSE calendar'),
        ('hse.performance', 'HSE performance'),
    ]),
    ('Other tools', [
        ('directory.clients', 'The client directory'),
        ('file_templates.library', 'The file template library'),
        ('time_tracking.log', 'Logging time'),
        ('blog.updates', 'Release updates'),
    ]),
    ('Wiki', [
        ('wiki.editor', 'Writing a wiki article'),
        ('wiki.help-keys', 'Help keys and coverage'),
    ]),
]

HELP_KEY_LABELS = {key: label for _, pairs in HELP_KEY_GROUPS for key, label in pairs}

HELP_KEYS = set(HELP_KEY_LABELS)


def label_for(key):
    """The human label for a key, or the key itself if it is not registered."""
    return HELP_KEY_LABELS.get(key, key)


def is_registered(key):
    return key in HELP_KEYS


def coverage(claimed_keys):
    """
    Work out what the Coverage panel shows, given the keys articles have claimed.
    Returns the totals, a row per group, and every key still unwritten.
    """
    claimed = {key for key in claimed_keys if key in HELP_KEYS}

    groups, missing = [], []
    for name, pairs in HELP_KEY_GROUPS:
        keys = [key for key, _ in pairs]
        written = [key for key in keys if key in claimed]
        groups.append({'name': name, 'written': len(written), 'total': len(keys)})
        missing.extend(
            {'key': key, 'label': HELP_KEY_LABELS[key], 'group': name}
            for key in keys if key not in claimed
        )

    return {
        'written': len(claimed),
        'total': len(HELP_KEYS),
        'groups': groups,
        'missing': missing,
    }
