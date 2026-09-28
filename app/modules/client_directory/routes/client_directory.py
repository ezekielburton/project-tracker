# Client Directory: the directory page plus two write routes, one for Client
# ("company") records and one for Contact records. Each write route creates or
# updates depending on whether the JSON body has an "id". A Client is the
# company; there is no separate Company model.

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Client, Contact
from app.modules.core.shared.lib.capabilities import can, require

client_directory_bp = Blueprint('client_directory', __name__, url_prefix='/directory/clients', template_folder='../templates')


# ── Directory page ──────────────────────────────────────────────────────

@client_directory_bp.route('')
@login_required
def index():
    """GET /directory/clients. Renders the directory page with every Client
    and its Contacts as one JSON blob; client_directory.js builds the list,
    search and detail panel from it."""
    clients = Client.query.order_by(Client.name).all()

    # Plain dicts so the template can |tojson them into a <script> constant.
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

    # Drives every Edit / Add affordance in the template and JS. Roles without
    # the capability get a read-only directory.
    can_edit = can('edit_client_directory', current_user)

    return render_template(
        'client_directory/index.html',
        directory_data=directory_data,
        can_edit=can_edit,
    )


# ── Company (Client) create/update ──────────────────────────────────────

@client_directory_bp.route('/companies', methods=['POST'])
@login_required
@require('edit_client_directory', real_user=True)
def save_company():
    """POST /directory/clients/companies. Creates a Client, or updates one
    when the body has an "id". The @require gate is the real security
    boundary; hiding buttons via can_edit is only UI."""
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

        # Exclude this row, or saving an unchanged name flags itself as a duplicate.
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

        # Set the created_by relationship, not created_by_id (app convention).
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
@require('edit_client_directory', real_user=True)
def save_contact():
    """POST /directory/clients/contacts. Creates a Contact, or updates one
    when the body has an "id". Also called (create only) by the project
    create overlay and the CS table's "+ Add new contact..." option."""
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
        # ── Update path ── client_id is ignored; a contact never moves company.
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
        # ── Create path ── client_id is required (Contact.client_id is not nullable).
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
