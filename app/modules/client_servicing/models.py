"""
Client Servicing data model. CS-only fields live on a 1:1 companion row to
Project; the shared Project model is never changed.
"""

from app.modules.core.shared.extensions import db


class ClientServicingScope(db.Model):
    """CS's own scope options, separate from the projects module's Scope.
    CS adds to it inline; admins can edit it."""
    __tablename__ = 'client_servicing_scopes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<ClientServicingScope {self.name}>'


class ClientServicing(db.Model):
    """1:1 companion row to a Project holding the CS master-sheet fields.
    Margin is derived, never stored (see margin_percent)."""
    __tablename__ = 'client_servicing'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False, unique=True,
    )

    lpo = db.Column(db.String(120), nullable=True)
    store_location = db.Column(db.String(255), nullable=True)
    removal_date = db.Column(db.Date, nullable=True)
    # Invoice month, stored as the 1st of the month. Monthly Summary buckets by it.
    invoice_month_date = db.Column(db.Date, nullable=True)
    cost_to_client = db.Column(db.Numeric(12, 2), nullable=True)
    inward_cost = db.Column(db.Numeric(12, 2), nullable=True)
    scope_id = db.Column(
        db.Integer, db.ForeignKey('client_servicing_scopes.id', ondelete='SET NULL'),
        nullable=True,
    )
    priority = db.Column(db.String(120), nullable=True)

    # Manual CS status overlay (a wider lifecycle than the platform's derived
    # status). None = use the derived status. See lib/status.py.
    cs_status = db.Column(db.String(40), nullable=True)

    # Installation-calendar annotations. risk overrides the derived risk;
    # None = auto. next_action / action_owner are free-text notes.
    risk = db.Column(db.String(20), nullable=True)
    next_action = db.Column(db.String(255), nullable=True)
    action_owner = db.Column(db.String(120), nullable=True)
    install_qty = db.Column(db.Integer, nullable=True)  # None = not filled in

    # Invoicing (finance-owned) fields.
    lpo_date = db.Column(db.Date, nullable=True)
    project_value = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_number = db.Column(db.String(120), nullable=True)
    invoice_date = db.Column(db.Date, nullable=True)
    invoice_amount = db.Column(db.Numeric(12, 2), nullable=True)
    gr_received = db.Column(db.Boolean, nullable=False, default=False)
    invoice_uploaded = db.Column(db.Boolean, nullable=False, default=False)
    validation_status = db.Column(db.String(20), nullable=True)

    # Closed lifecycle (CS-owned). closed_at marks the project closed and sets
    # its closing month. invoice_needed is the cancelled flow's answer; None = never asked.
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    invoice_needed = db.Column(db.Boolean, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    project = db.relationship('Project', backref=db.backref('client_servicing', uselist=False))
    scope = db.relationship('ClientServicingScope')
    closed_by = db.relationship('User', foreign_keys=[closed_by_id])

    @property
    def margin_percent(self):
        """(cost_to_client - inward_cost) / cost_to_client as a percentage.
        None if either figure is missing or cost_to_client is zero."""
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

    @property
    def is_closed(self):
        """True once the project is closed. Closing is final; nothing clears closed_at."""
        return self.closed_at is not None

    @property
    def close_invoice_state(self):
        """Invoice state for the Closed page: 'not_needed' when the cancelled
        flow answered no, 'invoiced' once invoice_date is set, else 'pending'."""
        if self.invoice_needed is False:
            return 'not_needed'
        if self.invoice_date:
            return 'invoiced'
        return 'pending'

    def __repr__(self):
        return f'<ClientServicing project_id={self.project_id}>'


class ClientServicingSetting(db.Model):
    """Single-row module settings: the Days Pending colour thresholds. Read
    via current(); admin/management edit it on Invoicing > By Project."""
    __tablename__ = 'client_servicing_settings'

    id = db.Column(db.Integer, primary_key=True)
    days_green_max = db.Column(db.Integer, nullable=False, default=30)
    days_red_max = db.Column(db.Integer, nullable=False, default=60)

    @classmethod
    def current(cls):
        """The saved row, or an unsaved default if none exists (reads never write)."""
        return cls.query.first() or cls(days_green_max=30, days_red_max=60)

    def __repr__(self):
        return f'<ClientServicingSetting green={self.days_green_max} red={self.days_red_max}>'
