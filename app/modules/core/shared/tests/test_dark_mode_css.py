"""Regression test for the 2.4.1 dark-mode colour sweep: the swept
stylesheets must route every hex colour through a CSS variable (so a dark
override actually reaches it) instead of hard-coding it again."""
import glob
import os
import re

SWEPT_FILES = [
    "main.css", "shared.css", "project_list.css", "project_overlay.css",
    "dashboard.css", "client_directory.css", "achievements.css",
    "time_tracking.css", "blog.css", "feedback.css", "wiki.css",
    "profile.css", "preview.css", "wizard.css", "drag-drop.css",
    "file-templates.css", "hse.css",
]

HEX_RE = re.compile(r'#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')


def _root_block_ranges(text):
    """Token *definitions* (:root and :root[data-theme="dark"]) are allowed
    to contain literal hex — only usages outside them are checked."""
    ranges = []
    for m in re.finditer(r':root(?:\[data-theme="dark"\])?\s*\{', text):
        start, depth, i = m.start(), 0, m.end() - 1
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    ranges.append((start, i + 1))
                    break
            i += 1
    return ranges


def _swept_path(app, fn):
    """Locate a swept CSS file wherever it now lives — assets are moving into
    per-module static folders (2.4.3), so search app/**/static/css/."""
    matches = glob.glob(os.path.join(app.root_path, '**', 'static', 'css', fn), recursive=True)
    assert matches, f"swept CSS file not found under app/: {fn}"
    return matches[0]


def test_no_hardcoded_hex_outside_tokens(app):
    offenders = {}
    for fn in SWEPT_FILES:
        path = _swept_path(app, fn)
        text = open(path, encoding='utf-8').read()
        roots = _root_block_ranges(text) if fn == "main.css" else []
        hits = [m.group(0) for m in HEX_RE.finditer(text)
                if not any(s <= m.start() < e for s, e in roots)]
        if hits:
            offenders[fn] = hits

    assert not offenders, (
        f"Hard-coded hex colours found outside CSS variables (breaks dark "
        f"mode for these): {offenders}"
    )
