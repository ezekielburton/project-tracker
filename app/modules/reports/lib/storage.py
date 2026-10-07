"""Where report PDFs live: on the server under uploads/reports/, with a copy
on the NAS. Files are named by run id, so a report made twice for the same
period never overwrites the earlier one."""
import os

from flask import current_app

from app.modules.core.shared.services.nas_outbox import upload_or_queue


def _stored_name(run):
    return f'{run.id}-{run.file_name}'


def _folder(run):
    return os.path.join(current_app.config['UPLOAD_FOLDER'], 'reports',
                        run.period_kind, str(run.period_start.year))


def path_for(run):
    return os.path.join(_folder(run), _stored_name(run))


def save(run, pdf_bytes):
    """Writes the PDF to the server, then copies it to the NAS (queued if the
    NAS is down). A failed NAS copy never fails the report."""
    os.makedirs(_folder(run), exist_ok=True)
    with open(path_for(run), 'wb') as fh:
        fh.write(pdf_bytes)
    root = current_app.config.get('NAS_REPORTS_ROOT', '/Admin/Reports')
    nas_folder = f'{root}/{run.period_start.year}/{run.period_kind.capitalize()}'
    try:
        upload_or_queue(pdf_bytes, nas_folder, _stored_name(run))
    except OSError as e:
        current_app.logger.warning(f'Report NAS copy failed for {run.file_name}: {e}')


def read(run):
    with open(path_for(run), 'rb') as fh:
        return fh.read()
