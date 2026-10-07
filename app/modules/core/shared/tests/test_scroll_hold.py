"""The shared scroll-hold helper: every page loads it, it offers
markScrollable(), and the wheel is only held while a box is scrollable."""
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1]


def test_every_page_loads_the_helper():
    base = (SHARED / 'templates' / 'base.html').read_text(encoding='utf-8')
    assert "filename='js/scroll_hold.js'" in base


def test_the_helper_marks_boxes_and_rechecks_on_navigation():
    script = (SHARED / 'static' / 'js' / 'scroll_hold.js').read_text(encoding='utf-8')
    assert 'window.markScrollable = function' in script
    assert "'.scroll-hold'" in script and "'is-scrollable'" in script
    assert "'helix:navigated'" in script


def test_the_wheel_is_held_only_while_the_box_overflows():
    css = (SHARED / 'static' / 'css' / 'shared.css').read_text(encoding='utf-8')
    assert '.scroll-hold.is-scrollable {\n    overscroll-behavior: contain;\n}' in css
    assert '.scroll-hold {' not in css  # the box itself never holds the wheel
