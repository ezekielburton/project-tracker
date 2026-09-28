from app.modules.core.shared.extensions import db
from datetime import datetime


# A client brand; also the "company" in the Client Directory.
class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_email = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Client Directory fields (all optional) ---

    # Comma-separated alternate names, matched by the directory search box.
    aliases = db.Column(db.String(500), nullable=True)

    # One-line office label, e.g. "DIFC, Dubai".
    office_location = db.Column(db.String(200), nullable=True)

    # Comma-separated installation sites, e.g. "MOE, DCC, MCC"; unbounded, so Text.
    installation_locations = db.Column(db.Text, nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<Client {self.name}>'


# ------ Client Directory ------
# A Contact is a person at a Client (company).

class Contact(db.Model):
    __tablename__ = 'contacts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(200), nullable=True)

    # Where this person is based; can differ from Client.office_location.
    location = db.Column(db.String(200), nullable=True)

    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)

    # No delete cascade: admin's delete_client deletes a Client's Contacts
    # itself, and refuses while projects or deliverable types still use it.
    client = db.relationship('Client', backref='contacts')

    def __repr__(self):
        return f'<Contact {self.name}>'


# A retail customer and its region.
class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
