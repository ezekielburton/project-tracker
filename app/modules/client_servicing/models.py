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

    # Manual operational-status overlay — the CS master-sheet lifecycle,
    # which is wider than the platform's derived status. None = fall back
    # to the derived status. See lib/status.py (never touches Project).
    cs_status = db.Column(db.String(40), nullable=True)

    # Installation-calendar overlay (CS annotations). risk is a manual
    # override of the derived risk (status-vs-install-date); None = auto.
    # next_action / action_owner are free-text notes shown on the calendar.
    risk = db.Column(db.String(20), nullable=True)
    next_action = db.Column(db.String(255), nullable=True)
    action_owner = db.Column(db.String(120), nullable=True)
    install_qty = db.Column(db.Integer, nullable=True)  # manual install quantity; None = not filled

    # Invoicing (finance-owned) fields.
    lpo_date = db.Column(db.Date, nullable=True)
    project_value = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_number = db.Column(db.String(120), nullable=True)
    invoice_date = db.Column(db.Date, nullable=True)
    invoice_amount = db.Column(db.Numeric(12, 2), nullable=True)
    gr_received = db.Column(db.Boolean, nullable=False, default=False)
    invoice_uploaded = db.Column(db.Boolean, nullable=False, default=False)
    validation_status = db.Column(db.String(20), nullable=True)

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

    @property
    def days_pending(self):
        """Days waiting: since invoice_date once invoiced, else since
        removal_date (ready to invoice). None when neither is set."""
        from datetime import date
        anchor = self.invoice_date or self.removal_date
        if anchor is None:
            return None
        return (date.today() - anchor).days

    def __repr__(self):
        return f'<ClientServicing project_id={self.project_id}>'


class ClientServicingSetting(db.Model):
    """Single-row module settings — currently the Days Pending colour
    thresholds. Read via current(); admin/management edit it on the
    Invoicing page."""
    __tablename__ = 'client_servicing_settings'

    id = db.Column(db.Integer, primary_key=True)
    days_green_max = db.Column(db.Integer, nullable=False, default=30)
    days_red_max = db.Column(db.Integer, nullable=False, default=60)

    @classmethod
    def current(cls):
        """The saved row, or a transient default instance if none exists —
        read-only callers never trigger a write."""
        return cls.query.first() or cls(days_green_max=30, days_red_max=60)

    def __repr__(self):
        return f'<ClientServicingSetting green={self.days_green_max} red={self.days_red_max}>'
