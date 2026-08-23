from app.modules.core.shared.extensions import db
from datetime import datetime


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_email = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Client Directory fields ---
    # These three back the Client Directory page's "company" detail view.
    # Client is doing double duty here: it's still the brand/client entity
    # used everywhere else in briefs, AND (since the Company model was
    # retired) it's also "the company" the directory page displays. All
    # three are nullable/optional - every Client row that predates this
    # feature has none of them set, and none are required for the rest of
    # the app (briefs, deliverables, etc.) to keep working.

    # Comma-separated alternate names/nicknames for this client, e.g.
    # "Acme, Acme Corp, Acme Industries" - matched against by the directory
    # page's search box. This existed on the old standalone Company model
    # and is being added here now that Client has absorbed that role -
    # without it, the directory's "search by alias" feature would have
    # nothing to search.
    aliases = db.Column(db.String(500), nullable=True)

    # Free-text office address/location, e.g. "DIFC, Dubai". Deliberately a
    # short String, not Text - this is meant to be a one-line label shown in
    # the detail panel, not a multi-line address block.
    office_location = db.Column(db.String(200), nullable=True)

    # Free-text list of installation locations, e.g. "MOE, DCC, MCC". Text
    # (not String) because unlike office_location this can realistically
    # grow into a longer comma-separated list as more sites are added, and
    # there's no fixed upper bound the way there is for a single address.
    installation_locations = db.Column(db.Text, nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<Client {self.name}>'

# Customer Class, stores customer and their region.


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# DeliverableType Class. Handles relationships for deliverable types, which are linked to clients and customers. Also stores reference images for deliverable types, which can be used in the project brief to help designers understand the requirements.


class Contact(db.Model):
    __tablename__ = 'contacts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)   # required - a contact with no name isn't useful
    phone = db.Column(db.String(50), nullable=True)     # optional - not every contact has a phone on file
    email = db.Column(db.String(200), nullable=True)    # optional, same reasoning as phone

    # Free-text location for this specific person, e.g. "DIFC, Dubai" - distinct
    # from Client.office_location above, since a contact can be based somewhere
    # different from their company's main office (a regional rep, someone
    # working from a different site, etc.). Optional, same reasoning as phone/email.
    location = db.Column(db.String(200), nullable=True)

    # Required (nullable=False): a Contact only exists in the context of a Client,
    # so this FK must always point somewhere - there's no such thing as a
    # "contact with no client" in this model. ForeignKey('clients.id') is what
    # actually creates the DB-level constraint linking this column to clients.id.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)

    # backref='contacts' lets any Client instance do `my_client.contacts` to get
    # its list of Contact rows, without declaring that side separately on Client.
    # No cascade='all, delete-orphan' here (unlike the old Company relationship) -
    # deliberately left as the SQLAlchemy default (nullable/no cascade), since
    # Client is a much older, more heavily-referenced model and automatically
    # deleting Contacts as a side effect of deleting a Client felt like more
    # surprising, harder-to-reverse behavior to bolt on quietly. If bulk-deleting
    # a Client's contacts along with it turns out to be desired later, this is
    # the line to revisit.
    client = db.relationship('Client', backref='contacts')

    def __repr__(self):
        return f'<Contact {self.name}>'
