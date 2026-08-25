# Client Directory blueprint: the directory page, plus the two write routes it
# (and the brief form) POST to — one for Client ("company") records, one for
# Contact records. Each route handles create AND update in a single endpoint,
# keyed off whether the JSON body includes an "id".
#
# A Client is the company; Contacts hang directly off the Client model. There
# is no separate Company model.

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Client, Contact
from app.modules.core.shared.lib.decorators import role_required

# The url_prefix lives on the blueprint, so every route below is relative to
# it — e.g. @route('/contacts') serves POST /directory/clients/contacts.
client_directory_bp = Blueprint('client_directory', __name__, url_prefix='/directory/clients', template_folder='../templates')


# ── Directory page ──────────────────────────────────────────────────────

@client_directory_bp.route('')
@login_required
def index():
    """
    GET /directory/clients

    Renders the two-column Client Directory page. Every Client, each with
    its nested Contacts, is fetched once here and handed to the template as
    a single JSON blob - client_directory.js renders the left panel, runs
    the search filter, and builds the right-panel detail view entirely from
    that one blob rather than round-tripping to the server for every click.
    Only the write actions (create/update) and the "Projects" linked list
    hit the server again after the page has loaded.
    """
    clients = Client.query.order_by(Client.name).all()

    # Built as a plain list of dicts, not passed as raw ORM objects, because
    # this gets embedded directly into the page as JSON via |tojson in the
    # template - see CLAUDE.md's "JS in templates" rule: JSON data always
    # goes into a <script> block as a JS constant, never stuffed into an
    # HTML attribute, since Flask's tojson filter doesn't escape " for that
    # context and it silently breaks JSON.parse the moment any field
    # contains a quote character.
    directory_data = [
        {
            'id': client.id,
            'name': client.name,
            'aliases': client.aliases or '',
            'office_location': client.office_location or '',
            'installation_locations': client.installation_locations or '',
            'contacts': [
                {
                    'id': contact.id,
                    'name': contact.name,
                    'phone': contact.phone or '',
                    'email': contact.email or '',
                    'location': contact.location or '',
                }
                for contact in client.contacts
            ],
        }
        for client in clients
    ]

    # Admin/Management/CS get full read-write on the directory; Designers
    # (and any other role) get read-only - no Edit button, no Add Company/
    # Add Contact affordances rendered at all. This single flag drives all
    # of that in the template/JS, so there's exactly one place to change if
    # the allowed role list ever changes, rather than current_user.role
    # checks scattered across the template and JS.
    can_edit = current_user.role in ('admin', 'management', 'cs')

    return render_template(
        'client_directory/index.html',
        directory_data=directory_data,
        can_edit=can_edit,
    )


# ── Company (Client) create/update ──────────────────────────────────────

@client_directory_bp.route('/companies', methods=['POST'])
@login_required
@role_required('admin', 'management', 'cs')
def save_company():
    """
    POST /directory/clients/companies

    Named "companies" in the URL to match the directory page's vocabulary -
    each row in the left panel is conceptually "a company" to whoever's
    using this page - even though the model underneath is Client. See the
    file-level comment above for why there's no separate Company model to
    route this to instead.

    Handles BOTH create and update from one endpoint, distinguished by
    whether the JSON body includes an "id":
      - no "id" (or a falsy one)  -> create a new Client
      - "id" present              -> update that existing Client's fields
    This is what the spec asked for directly (one route, both verbs) rather
    than a separate update/PATCH route - the directory page's Save button
    doesn't need to know or care which case it's in; it always POSTs here.

    @role_required enforces server-side what the frontend also hides in the
    UI via the can_edit flag from index() above - hiding the Edit/Add
    buttons is a convenience for Designers, not the actual security
    boundary. A Designer who somehow fired this request directly would
    still get a 403 here, same as any other write route in this app.
    """
    from app.modules.core.shared.lib.utils import log_activity, get_actor

    data = request.get_json()
    name = (data.get('name') or '').strip()
    aliases = (data.get('aliases') or '').strip() or None
    office_location = (data.get('office_location') or '').strip() or None
    installation_locations = (data.get('installation_locations') or '').strip() or None
    client_id = data.get('id')

    if not name:
        return jsonify({'success': False, 'error': 'Company name is required'}), 400

    if client_id:
        # ── Update path ──
        client = Client.query.get(int(client_id))
        if not client:
            return jsonify({'success': False, 'error': 'Company not found'}), 404

        # Uniqueness check excludes the row being edited itself
        # (Client.id != client.id) - otherwise saving a company with its OWN
        # unchanged name would incorrectly flag itself as a duplicate of...
        # itself.
        conflict = Client.query.filter(Client.name == name, Client.id != client.id).first()
        if conflict:
            return jsonify({'success': False, 'error': 'A company with this name already exists'}), 400

        client.name = name
        client.aliases = aliases
        client.office_location = office_location
        client.installation_locations = installation_locations
        db.session.commit()

        log_activity(
            'company_updated', f'Company "{client.name}" updated',
            user=get_actor(), entity_type='company', entity_name=client.name, entity_id=client.id
        )
    else:
        # ── Create path ──
        if Client.query.filter_by(name=name).first():
            return jsonify({'success': False, 'error': 'A company with this name already exists'}), 400

        # created_by=get_actor() (the object), not created_by_id=...id (the
        # int) - matches the "DB Facts" convention in CLAUDE.md used
        # everywhere else a creator relationship is set on a new row.
        client = Client(
            name=name, aliases=aliases,
            office_location=office_location, installation_locations=installation_locations,
            created_by=get_actor()
        )
        db.session.add(client)
        db.session.commit()

        log_activity(
            'company_created', f'Company "{client.name}" added to the client directory',
            user=get_actor(), entity_type='company', entity_name=client.name, entity_id=client.id
        )

    return jsonify({'success': True, 'company': {
        'id': client.id, 'name': client.name, 'aliases': client.aliases or '',
        'office_location': client.office_location or '',
        'installation_locations': client.installation_locations or '',
    }})


# ── Contact create/update ────────────────────────────────────────────────

@client_directory_bp.route('/contacts', methods=['POST'])
@login_required
@role_required('admin', 'management', 'cs')
def save_contact():
    """
    POST /directory/clients/contacts

    Same create-or-update-by-id shape as save_company() above. Used by:
      - the directory page's per-company "Add Contact" modal (create), and
        the contact detail panel's Save button (update)
      - the brief form's "+ Add New Contact" / "Add new contact..." flow
        (create only)

    Note this route is now @role_required('admin', 'management', 'cs')
    where it used to be @login_required only. In practice this changes
    nothing for the brief-form call site - /projects/create itself is
    already gated to those same three roles, so a Designer could never
    have reached this form to call it anyway - but it brings the route's
    own permission check in line with what the directory page's edit
    surface actually needs, rather than leaving it more permissive than
    every other write route in this file.
    """
    from app.modules.core.shared.lib.utils import log_activity, get_actor

    data = request.get_json()
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip() or None
    email = (data.get('email') or '').strip() or None
    location = (data.get('location') or '').strip() or None
    client_id = data.get('client_id')
    contact_id = data.get('id')

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    if contact_id:
        # ── Update path ── client_id is deliberately NOT required here:
        # editing an existing contact's own details doesn't move them to a
        # different company - reassigning a contact to another Client isn't
        # part of this spec, so that field is simply left untouched on update.
        contact = Contact.query.get(int(contact_id))
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404

        contact.name = name
        contact.phone = phone
        contact.email = email
        contact.location = location
        db.session.commit()

        log_activity(
            'contact_updated', f'Contact "{contact.name}" updated',
            user=get_actor(), entity_type='contact', entity_name=contact.name, entity_id=contact.id
        )
    else:
        # ── Create path ── client_id IS required here - a brand new Contact
        # has to belong to some Client from the moment it's created, since
        # Contact.client_id is nullable=False at the model level.
        if not client_id:
            return jsonify({'success': False, 'error': 'Name and client are required'}), 400

        client = Client.query.get(int(client_id))
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        contact = Contact(name=name, phone=phone, email=email, location=location, client_id=client.id)
        db.session.add(contact)
        db.session.commit()

        log_activity(
            'contact_created', f'Contact "{contact.name}" added under "{client.name}"',
            user=get_actor(), entity_type='contact', entity_name=contact.name, entity_id=contact.id
        )

    return jsonify({'success': True, 'contact': {
        'id': contact.id, 'name': contact.name, 'phone': contact.phone or '',
        'email': contact.email or '', 'location': contact.location or '',
        'client_id': contact.client_id,
    }})
