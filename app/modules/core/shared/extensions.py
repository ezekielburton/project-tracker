"""Shared Flask extension singletons: SQLAlchemy, Flask-Login and Flask-Mail.

create_app() binds them to the app; every module imports these same instances.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()