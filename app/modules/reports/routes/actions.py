"""Reports actions: preview, make, send and download, and the recipient and
auto-send settings. JSON routes answer a 403 body; file routes a 403 page."""
import io
import os
from datetime import date, datetime

from flask import abort, jsonify, request, send_file
from flask_login import current_user, login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import require, require_api
from app.modules.core.shared.lib.timezone import dubai_today
from app.modules.core.shared.models import User
from app.modules.reports.lib import pdf, send, settings, storage
from app.modules.reports.lib.build import build
from app.modules.reports.lib.period import Period
from app.modules.reports.models import ALL_REPORTS, PERIOD_KINDS, REPORTS, ReportRun
from app.modules.reports.routes.blueprint import reports_bp

GATE = 'admin_panel'


def _period(kind, start):
    """The period a form asked for, or None when it's not a real one."""
    if kind not in PERIOD_KINDS:
        return None
    try:
        return Period.of(kind, date.fromisoformat(start or ''))
    except ValueError:
        return None


def _error(message, status=400):
    return jsonify({'success': False, 'error': message}), status


@reports_bp.route('/preview')
@login_required
@require(GATE, real_user=True)
def preview():
    """One report as a PDF in the browser. Not stored, not sent."""
    period = _period(request.args.get('kind'), request.args.get('start'))
    report = request.args.get('report')
    if period is None or report not in REPORTS:
        abort(400)
    data = pdf.render_pdf(report, build(period, dubai_today()), datetime.utcnow())
    return send_file(io.BytesIO(data), mimetype='application/pdf',
                     download_name=pdf.file_name(report, period))


@reports_bp.route('/runs/<int:run_id>/download')
@login_required
@require(GATE, real_user=True)
def download(run_id):
    """A stored report. ?view=1 opens it in the browser instead."""
    run = db.get_or_404(ReportRun, run_id)
    path = storage.path_for(run)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype='application/pdf', download_name=run.file_name,
                     as_attachment=request.args.get('view') != '1')


@reports_bp.route('/api/generate', methods=['POST'])
@require_api(GATE, real_user=True)
def api_generate():
    """Makes and stores the chosen reports; with send=true also emails them."""
    data = request.get_json(silent=True) or {}
    period = _period(data.get('kind'), data.get('start'))
    reports = [r for r in REPORTS if r in (data.get('reports') or [])]
    if period is None or not reports:
        return _error('Pick a period and at least one report.')
    runs = send.generate(period, reports, made_by=current_user._get_current_object())
    if data.get('send'):
        send.deliver(runs)
    return jsonify({'success': True, 'runs': [{'id': r.id, 'status': r.status, 'error': r.error}
                                              for r in runs]})


@reports_bp.route('/api/runs/<int:run_id>/send', methods=['POST'])
@require_api(GATE, real_user=True)
def api_send_run(run_id):
    """Sends a stored report to its current recipients."""
    run = db.get_or_404(ReportRun, run_id)
    if not os.path.exists(storage.path_for(run)):
        return _error('The stored PDF is missing.', 404)
    send.deliver([run])
    return jsonify({'success': run.status == 'sent', 'status': run.status, 'error': run.error})


@reports_bp.route('/api/recipients', methods=['POST'])
@require_api(GATE, real_user=True)
def api_recipients():
    """{report, user_id, add}: adds or removes one recipient."""
    data = request.get_json(silent=True) or {}
    user = db.session.get(User, data.get('user_id')) if isinstance(data.get('user_id'), int) else None
    if data.get('report') not in REPORTS or user is None or not user.is_active:
        return _error('Pick a report and an active person.')
    if data.get('add'):
        settings.add_recipient(data['report'], user)
    else:
        settings.remove_recipient(data['report'], user)
    return jsonify({'success': True})


@reports_bp.route('/api/auto-send', methods=['POST'])
@require_api(GATE, real_user=True)
def api_auto_send():
    """{report, kind, enabled}: one auto-send switch; report 'all' is the master."""
    data = request.get_json(silent=True) or {}
    report, kind = data.get('report'), data.get('kind')
    if (report not in REPORTS and report != ALL_REPORTS) or kind not in PERIOD_KINDS:
        return _error('Unknown switch.')
    settings.set_auto_send(report, kind, bool(data.get('enabled')))
    return jsonify({'success': True})
