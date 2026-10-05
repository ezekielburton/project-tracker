"""Which wiki sections are for the reader's role. Relevance only: nothing is hidden."""
from app.modules.core.shared.lib.capabilities import ROLE_LABELS, can, role_label

SCOPE_MINE = 'mine'
SCOPE_ALL = 'all'

# Saved values may be keys or display labels in any case, e.g. 'cs', 'CS', 'Team Lead'.
_KEY_BY_NAME = {**{label.lower(): key for key, label in ROLE_LABELS.items()},
                **{key.lower(): key for key in ROLE_LABELS}}


def section_roles(section):
    """The role keys a section is for. Saved keys are used as they are, older label
    values are matched back to keys, and anything unrecognised is ignored."""
    keys = []
    for value in (getattr(section, 'relevant_roles', None) or '').split(','):
        value = value.strip()
        key = _KEY_BY_NAME.get(value.lower())
        if key and key not in keys:
            keys.append(key)
    return keys


def is_for(section, role):
    """True when the section names no roles (so everyone) or names this one."""
    roles = section_roles(section)
    return not roles or role in roles


def roles_text(section):
    """A section's roles as display labels, e.g. 'Client Servicing, Designer'."""
    return ', '.join(role_label(key) for key in section_roles(section))


def default_scope():
    """Everything for people who manage the wiki; the reader's own role for everyone else."""
    return SCOPE_ALL if can('manage_wiki') else SCOPE_MINE


def reader_scope(requested):
    """The scope the link asked for, or the reader's default."""
    return requested if requested in (SCOPE_MINE, SCOPE_ALL) else default_scope()


def scope_param(scope):
    """The scope to carry in links: only when it differs from the reader's default,
    so starting or stopping emulation lands on the new reader's own default."""
    return None if scope == default_scope() else scope


def dimmed_sections(sections, role, scope):
    """Ids of the sections to dim: other roles' sections, only while scoped to the reader's role."""
    if scope == SCOPE_ALL:
        return set()
    return {section.id for section in sections if not is_for(section, role)}


def order_hits(hits, role, scope):
    """Search hits with the reader's role first while scoped to it. Each group keeps match order."""
    if scope == SCOPE_ALL:
        return list(hits)
    mine = [hit for hit in hits if is_for(hit.section, role)]
    others = [hit for hit in hits if not is_for(hit.section, role)]
    return mine + others
