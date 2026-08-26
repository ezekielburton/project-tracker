"""Root pytest configuration: re-export the shared fixtures from core/shared so
pytest makes them available to every test in the project."""
from app.modules.core.shared.testing import app, client, db_session  # noqa: F401