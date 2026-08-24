""" 
Test: the app factory build cleanly, the ORM configures across the split
model package, and the shared base templates resolve from core/shared.

"""
import sqlalchemy as sa

def test_app_boots(app):
    assert app is not None

def test_mappers_configure(app):
    # Raises if any relationship across the split model package is misconfigured
    sa.orm.configure_mappers()

def test_shared_templates_resolve(app):
    for name in ('base.html', 'base_fragment.html', '_macros.html', '_shared_macros.html',
                 'partials/avatar_crop_modal.html'):
        assert app.jinja_env.get_template(name) is not None