# Small JSON endpoints under /api: zip downloads, the static version stamp
# (polling.js's redeploy check) and Client Directory lookups.

from flask import Blueprint, jsonify, current_app
from flask_login import login_required
from app.modules.core.shared.models import Project, Client, Contact

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/zip-download/<zip_id>')
@login_required
def zip_download(zip_id):
    """Serve a zip built by zip_utils.build_zip(), then delete it. Shared by
    every "Download All" button."""
    from flask import abort
    from app.modules.core.shared.lib.zip_utils import serve_zip

    response = serve_zip(zip_id)
    if response is None:
        abort(404)
    return response

@api_bp.route('/version')
def app_version():
    return jsonify(version=current_app.config['STATIC_VERSION'])


@api_bp.route('/clients/<int:client_id>/contacts')
@login_required
def client_contacts(client_id):
    """GET /api/clients/<client_id>/contacts -> [{"id", "name"}], for the
    Client Directory's contact dropdown. Any logged-in user."""
    from flask import abort

    client = Client.query.get(client_id)
    if not client:
        abort(404)

    contacts = Contact.query.filter_by(client_id=client.id).order_by(Contact.name).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in contacts])


def _directory_project_entry(p):
    """Project shape for the directory's linked-projects lists. status_label
    matches the templates' `replace('_', ' ') | title` format."""
    return {
        'id': p.id,
        'name': p.name,
        'status': p.project_status,
        'status_label': (p.project_status or '').replace('_', ' ').title(),
    }


@api_bp.route('/clients/<int:client_id>/projects')
@login_required
def client_projects(client_id):
    """GET /api/clients/<client_id>/projects: a company's projects for the
    Client Directory. Any logged-in user (designers see it read-only)."""
    from flask import abort

    client = Client.query.get(client_id)
    if not client:
        abort(404)

    projects = Project.query.filter_by(client_id=client.id).order_by(Project.created_at.desc()).all()
    return jsonify([_directory_project_entry(p) for p in projects])




@api_bp.route('/contacts/<int:contact_id>/projects')
@login_required
def contact_projects(contact_id):
    """GET /api/contacts/<contact_id>/projects: same, for one contact."""
    from flask import abort

    contact = Contact.query.get(contact_id)
    if not contact:
        abort(404)

    projects = Project.query.filter_by(contact_id=contact.id).order_by(Project.created_at.desc()).all()
    return jsonify([_directory_project_entry(p) for p in projects])
