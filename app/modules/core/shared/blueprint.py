"""The core/shared blueprint. No routes: it puts core/shared's templates on
Jinja's search path (shared base layout and macros) and serves shared static
files at /core/static.
"""
from flask import Blueprint

core = Blueprint('core', __name__, template_folder='templates', static_folder='static', static_url_path='/core/static')
