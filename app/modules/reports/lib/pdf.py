"""Renders a report to PDF with WeasyPrint. The page is a Jinja template;
fonts come from core/shared's print fonts so the PDF looks the same anywhere."""
import os

from flask import current_app, render_template

from app.modules.core.shared.lib.timezone import to_dubai
from app.modules.reports.lib.people import DEPARTMENT_REPORTS
from app.modules.reports.models import REPORTS

TEMPLATE = 'reports/pdf/report.html'


def file_name(report, period):
    """'OVP-Wk40-Client-Servicing.pdf'."""
    return f"OVP-{period.file_stem}-{REPORTS[report].replace(' ', '-')}.pdf"


def _stamp(made_at_utc):
    """'Mon 5 Oct, 08:00' in Dubai time."""
    local = to_dubai(made_at_utc)
    return f'{local:%a} {local.day} {local:%b, %H:%M}'


def context(report, built, made_at_utc):
    """Everything report.html needs."""
    names = {r['user'].id: r['user'].name for key in DEPARTMENT_REPORTS for r in built[key]['rows']}
    return {
        'report': report, 'label': REPORTS[report], 'data': built[report], 'built': built,
        'period': built[report]['period'], 'generated': _stamp(made_at_utc), 'names': names,
        'department_labels': {key: REPORTS[key] for key in DEPARTMENT_REPORTS},
    }


def render_html(report, built, made_at_utc):
    return render_template(TEMPLATE, **context(report, built, made_at_utc))


def render_pdf(report, built, made_at_utc):
    """The PDF as bytes."""
    from weasyprint import HTML  # here, not at import: it needs system libraries (Pango)
    base = os.path.join(current_app.root_path, 'modules', 'core', 'shared', 'static') + os.sep
    return HTML(string=render_html(report, built, made_at_utc), base_url=base).write_pdf()
