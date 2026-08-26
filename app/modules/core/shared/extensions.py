"""

Shared flash extension instances.

The SQLAlchemy database handle, Flask-Login manager and the Flask-Mail
sender are created here as unbound singletone. The application factory
binds them to the app at startup, and every module imports these same instances so
the whole application shares one database registry, one login managee and one
mail sender.

"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()