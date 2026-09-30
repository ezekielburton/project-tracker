"""
Resets every saved Client Servicing table layout to the default column order,
keeping each column's saved width. Run once when the default order changes.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.modules.core.shared.models import UserTableLayout
from app.modules.client_servicing.routes.table import TABLE_KEY, reset_to_default_order

app = create_app()
with app.app_context():
    rows = UserTableLayout.query.filter_by(table_key=TABLE_KEY).all()
    for row in rows:
        row.layout = reset_to_default_order(row.layout)
    db.session.commit()
    print('Reset column order on {} saved layout(s).'.format(len(rows)))
