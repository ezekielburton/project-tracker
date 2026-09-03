"""
Client Servicing module — data model. The CS-only fields live here, not on
the shared Project, per the module boundary: this is a 1:1 companion row
that extends a project, never a change to the shared model.
"""

from app.modules.core.shared.extensions import db


class ClientServicingScope(db.Model):
    """CS's own scope option list — separate from the projects module's
    Scope. CS adds to it inline; also admin-editable."""
    __tablename__ = 'client_servicing_scopes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<ClientServicingScope {self.name}>'


class ClientServicing(db.Model):
    """1:1 companion row to a Project, holding the CS master-sheet fields
    that don't belong on the shared model. Margin is derived, never
    stored — see margin_percent."""
    __tablename__ = 'client_servicing'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False, unique=True,
    )

    lpo = db.Column(db.String(120), nullable=True)
    store_location = db.Column(db.String(255), nullable=True)
    removal_date = db.Column(db.Date, nullable=True)
    invoice_month = db.Column(db.String(20), nullable=True)
    cost_to_client = db.Column(db.Numeric(12, 2), nullable=True)
    inward_cost = db.Column(db.Numeric(12, 2), nullable=True)
    scope_id = db.Column(
        db.Integer, db.ForeignKey('client_servicing_scopes.id', ondelete='SET NULL'),
        nullable=True,
    )
    priority = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    project = db.relationship('Project', backref=db.backref('client_servicing', uselist=False))
    scope = db.relationship('ClientServicingScope')

    @property
    def margin_percent(self):
        """(cost_to_client - inward_cost) / cost_to_client as a percentage.
        None whenever either figure is missing or cost_to_client is zero,
        so callers never hit a divide-by-zero."""
        if self.cost_to_client is None or self.inward_cost is None:
            return None
        if self.cost_to_client == 0:
            return None
        return float((self.cost_to_client - self.inward_cost) / self.cost_to_client) * 100

    def __repr__(self):
        return f'<ClientServicing project_id={self.project_id}>'
