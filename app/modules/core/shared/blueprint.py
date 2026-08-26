"""The core/shared blueprint.

It registers no routes. Its purpose is to place core/shared's templates on
Jinja's search path so every module can extend the shared base layout and
import the shared macros. (When shared static is centralised here later, this
same blueprint gains a static_folder to serve those assets.)
"""
from flask import Blueprint

core = Blueprint('core', __name__, template_folder='templates')
