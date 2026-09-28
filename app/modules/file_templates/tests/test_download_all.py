"""Download All buttons: the build routes zip the uploaded templates and hand
back a one-shot /api/zip-download URL."""
import io
import zipfile

from app.modules.core.shared.models import User, Client, Customer, DeliverableType
from app.modules.core.shared.testing import login_as

FOLDER_ATTR = 'app.modules.file_templates.routes.file_templates.template_upload_folder'


def _setup(db_session, tmp_path, tag):
    user = User(name='FT User', email=f'ft-zip-{tag}@example.com', role='designer')
    user.set_password('pw123456')
    db_session.add(user)
    db_session.flush()
    client_row = Client(name=f'FT Client {tag}', created_by_id=user.id)
    customer = Customer(name=f'FT Customer {tag}', region='oman')
    db_session.add_all([client_row, customer])
    db_session.flush()
    with_file = DeliverableType(name='Gondola', client_id=client_row.id, customer_id=customer.id,
                                template_filename=f'ft-{tag}.ai', is_active=True)
    no_file = DeliverableType(name='Wobbler', client_id=client_row.id, customer_id=customer.id,
                              is_active=True)
    db_session.add_all([with_file, no_file])
    db_session.commit()
    (tmp_path / f'ft-{tag}.ai').write_bytes(b'AI-BYTES')
    return user, customer


def _download(client, build_url):
    resp = client.get(build_url)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    zip_resp = client.get(data['download_url'])
    assert zip_resp.status_code == 200
    return zipfile.ZipFile(io.BytesIO(zip_resp.data))


def test_customer_download_all_zips_uploaded_templates(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, lambda: str(tmp_path))
    user, customer = _setup(db_session, tmp_path, 'cust')
    login_as(client, app, user, 'pw123456')

    zf = _download(client, f'/file-templates/download-all/customer/{customer.id}')
    assert zf.namelist() == ['Gondola.ai']
    assert zf.read('Gondola.ai') == b'AI-BYTES'


def test_region_download_all_nests_by_customer(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, lambda: str(tmp_path))
    user, customer = _setup(db_session, tmp_path, 'region')
    login_as(client, app, user, 'pw123456')

    zf = _download(client, '/file-templates/download-all/region/oman')
    assert f'{customer.name}/Gondola.ai' in zf.namelist()


def test_download_all_with_no_files_returns_error(app, client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(FOLDER_ATTR, lambda: str(tmp_path / 'empty'))
    user, customer = _setup(db_session, tmp_path, 'none')
    login_as(client, app, user, 'pw123456')

    resp = client.get(f'/file-templates/download-all/customer/{customer.id}')
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_unknown_region_404s(app, client, db_session, monkeypatch, tmp_path):
    user, _ = _setup(db_session, tmp_path, 'bad')
    login_as(client, app, user, 'pw123456')
    assert client.get('/file-templates/download-all/region/mars').status_code == 404
