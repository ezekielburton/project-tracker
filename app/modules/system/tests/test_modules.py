"""A request's module comes from its blueprint's package, labelled as in the sidebar."""
from app.modules.system.lib import modules


def test_module_key_reads_the_package():
    assert modules.module_key('app.modules.wiki.routes.wiki') == 'wiki'
    assert modules.module_key('flask_login') is None


def test_labels_match_the_sidebar_or_read_from_the_key():
    assert modules.label('hse') == 'HSE & Compliance'
    assert modules.label('time_tracking') == 'Time Tracking'


def test_every_app_blueprint_gets_a_label(app):
    with app.app_context():
        labels = modules.blueprint_labels()
    assert labels['projects'] == 'Dashboard'  # the dashboard module's blueprint
    assert labels['wiki'] == 'Wiki'
