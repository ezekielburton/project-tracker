"""
Skeletons offered when creating a wiki article, as Editor.js documents.
Kept in code rather than the database — only admins write articles.
"""

from app.modules.wiki.lib.blocks import EDITORJS_VERSION


def _header(text):
    return {'type': 'header', 'data': {'text': text, 'level': 3}}


def _paragraph(text=''):
    return {'type': 'paragraph', 'data': {'text': text}}


def _list(items):
    return {'type': 'list', 'data': {'style': 'unordered', 'items': items}}


def _callout(text, variant='default'):
    return {'type': 'helixCallout', 'data': {'text': text, 'variant': variant}}


def _document(blocks):
    return {'time': 0, 'blocks': blocks, 'version': EDITORJS_VERSION}


ARTICLE_TEMPLATES = [
    {
        'key': 'how-to',
        'label': 'How-to',
        'description': "What it is, who it's for, the steps, a short clip, the gotchas.",
        'document': _document([
            _header('What it is'),
            _paragraph('One or two sentences, in plain words.'),
            _header("Who it's for"),
            _paragraph('The roles that do this task.'),
            _header('Steps'),
            _list(['First step', 'Second step', 'Third step']),
            _header('Watch it'),
            _paragraph('Drop a short screen capture here.'),
            _header('Gotchas'),
            _callout('The thing people get wrong, and what to do instead.'),
        ]),
    },
    {
        'key': 'reference',
        'label': 'Reference',
        'description': 'Every field on a screen or form, and what it means.',
        'document': _document([
            _header('What this screen is'),
            _paragraph('One sentence on where it lives and what it does.'),
            _header('Fields'),
            _list([
                'Field name — what it means, and what happens if you change it',
                'Field name — what it means',
            ]),
            _header('Gotchas'),
            _callout('Anything that behaves differently from how it looks.'),
        ]),
    },
    {
        'key': 'blank',
        'label': 'Blank',
        'description': 'Start with nothing.',
        'document': _document([]),
    },
]

TEMPLATE_KEYS = {template['key'] for template in ARTICLE_TEMPLATES}


def template_document(key):
    """The document for a template key; an empty document for anything else."""
    for template in ARTICLE_TEMPLATES:
        if template['key'] == key:
            return template['document']
    return _document([])


def picker_options():
    """The templates as the picker needs them — no documents, which the page sends separately."""
    return [
        {'key': t['key'], 'label': t['label'], 'description': t['description']}
        for t in ARTICLE_TEMPLATES
    ]
