# C&CM File Templates library — a standalone (not project-specific) browse
# page for downloadable per-store design template files (.ai), organized
# Region -> Customer -> DeliverableType. Templates are small files kept on
# local server disk (app/file_templates/), not the NAS.

import os
from flask import Blueprint, render_template
from flask_login import login_required
from app.modules.core.shared.models import Customer, DeliverableType
from app.modules.core.shared.lib.paths import template_upload_folder

file_templates_bp = Blueprint('file_templates', __name__, template_folder='../templates')

# Same region set used across the app — UAE first, then the Gulf countries.
REGIONS = [
    ('uae', 'UAE'),
    ('kuwait', 'Kuwait'),
    ('qatar', 'Qatar'),
    ('bahrain', 'Bahrain'),
    ('oman', 'Oman'),
]


@file_templates_bp.route('/file-templates')
@login_required
def index():
    """
    Builds a Region -> Customer -> DeliverableType structure for the page.
    Inactive deliverable types are excluded (matches how is_active is
    already treated elsewhere). Deliverable types with no uploaded
    template still appear, as a placeholder an admin can fill in later.
    Customers/regions with zero deliverable types at all are skipped —
    nothing meaningful to show or click into.
    """
    regions_data = []
    for region_key, region_label in REGIONS:
        customers = Customer.query.filter_by(region=region_key).order_by(Customer.name).all()
        customer_rows = []
        for customer in customers:
            deliverable_types = (
                DeliverableType.query
                .filter_by(customer_id=customer.id, is_active=True)
                .order_by(DeliverableType.name)
                .all()
            )
            if not deliverable_types:
                continue
            customer_rows.append({'customer': customer, 'deliverable_types': deliverable_types})

        if not customer_rows:
            continue
        regions_data.append({'region_key': region_key, 'region_label': region_label, 'customers': customer_rows})

    return render_template('file_templates/index.html', regions_data=regions_data)

@file_templates_bp.route('/file-templates/download/<int:deliverable_type_id>')
@login_required
def download_template(deliverable_type_id):
    """Downloads a single deliverable type's template file from local disk."""
    from flask import send_from_directory, abort

    dt = DeliverableType.query.get_or_404(deliverable_type_id)
    if not dt.template_filename:
        abort(404)

    ext = os.path.splitext(dt.template_filename)[1]
    return send_from_directory(
        template_upload_folder(), dt.template_filename,
        as_attachment=True, download_name=f'{dt.name}{ext}'
    )


@file_templates_bp.route('/file-templates/download-all/customer/<int:customer_id>')
@login_required
def download_all_customer_templates(customer_id):
    """Zips every uploaded template for one customer's deliverable types."""
    from flask import jsonify, url_for
    from app.modules.core.shared.lib.zip_utils import build_zip

    customer = Customer.query.get_or_404(customer_id)
    deliverable_types = DeliverableType.query.filter_by(customer_id=customer_id, is_active=True).all()

    zip_files = []
    for dt in deliverable_types:
        if not dt.template_filename:
            continue
        file_path = os.path.join(template_upload_folder(), dt.template_filename)
        if not os.path.exists(file_path):
            continue
        with open(file_path, 'rb') as f:
            content = f.read()
        ext = os.path.splitext(dt.template_filename)[1]
        zip_files.append((f'{dt.name}{ext}', content))

    if not zip_files:
        return jsonify({'success': False, 'error': 'No templates uploaded for this customer yet.'}), 400

    zip_id = build_zip(zip_files, f'{customer.name} - Templates.zip')
    return jsonify({'success': True, 'download_url': url_for('api.zip_download', zip_id=zip_id)})


@file_templates_bp.route('/file-templates/download-all/region/<region_key>')
@login_required
def download_all_region_templates(region_key):
    """Zips every uploaded template across all customers in a region,
    nesting each customer as its own subfolder inside the zip."""
    from flask import jsonify, url_for, abort
    from app.modules.core.shared.lib.zip_utils import build_zip

    region_label = dict(REGIONS).get(region_key)
    if not region_label:
        abort(404)

    customers = Customer.query.filter_by(region=region_key).order_by(Customer.name).all()

    zip_files = []
    for customer in customers:
        deliverable_types = DeliverableType.query.filter_by(customer_id=customer.id, is_active=True).all()
        for dt in deliverable_types:
            if not dt.template_filename:
                continue
            file_path = os.path.join(template_upload_folder(), dt.template_filename)
            if not os.path.exists(file_path):
                continue
            with open(file_path, 'rb') as f:
                content = f.read()
            ext = os.path.splitext(dt.template_filename)[1]
            zip_files.append((f'{customer.name}/{dt.name}{ext}', content))

    if not zip_files:
        return jsonify({'success': False, 'error': 'No templates uploaded for this region yet.'}), 400

    zip_id = build_zip(zip_files, f'{region_label} - Templates.zip')
    return jsonify({'success': True, 'download_url': url_for('api.zip_download', zip_id=zip_id)})

@file_templates_bp.route('/file-templates/simulatin-files-link')
@login_required
def get_simulation_files_link():
    """
    Returns a Synology Drive deep link for the fixed Simulation Files folder
    on the NAS — not project-specific, the same folder for everyone. The link
    is resolved through a live NAS API call rather than a static URL template
    (see build_drive_folder_url in the shared nas service).
    """
    from flask import jsonify
    from app.modules.core.shared.services.nas import build_drive_folder_url

    folder_path = '/Docs and Templates/Templates/Simulation Files'
    url = build_drive_folder_url(folder_path)
    if not url:
        return jsonify({'success': False, 'error': 'Could not reach the NAS.'}), 502

    return jsonify({'success': True, 'url': url, 'path': folder_path})