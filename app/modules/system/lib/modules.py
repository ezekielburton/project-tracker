"""Which module a request belongs to, from its blueprint: every blueprint
lives under app/modules/<module>/. Labels match the sidebar."""
from flask import current_app
from sqlalchemy import case

LABELS = {
    'admin': 'Admin Panel',
    'blog': 'App Update Blog',
    'client_directory': 'Client Directory',
    'client_servicing': 'Client Servicing',
    'dashboard': 'Dashboard',
    'digital_innovation': 'Digital Innovation',
    'file_templates': 'File Templates',
    'hse': 'HSE & Compliance',
    'projects': 'Projects',
    'reports': 'Reports',
    'wiki': 'Wiki',
}
OTHER = 'Other'


def module_key(import_name):
    """'app.modules.wiki.routes.wiki' -> 'wiki'; None outside app/modules."""
    parts = import_name.split('.')
    if 'modules' not in parts or parts.index('modules') + 1 >= len(parts):
        return None
    return parts[parts.index('modules') + 1]


def label(key):
    return LABELS.get(key) or key.replace('_', ' ').title()


def blueprint_labels():
    """{blueprint name: module label} for the running app."""
    labels = {}
    for name, blueprint in current_app.blueprints.items():
        key = module_key(blueprint.import_name)
        if key:
            labels[name] = label(key)
    return labels


def module_column(blueprint_column):
    """A SQL expression giving the module label for a blueprint column."""
    return case(blueprint_labels(), value=blueprint_column, else_=OTHER)
