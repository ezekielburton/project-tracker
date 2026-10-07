"""lib/pdf.py: every report renders, and the PDF builds where WeasyPrint is installed."""
from datetime import date, datetime

import pytest

from app.modules.reports.lib.build import build
from app.modules.reports.lib.pdf import file_name, render_html, render_pdf
from app.modules.reports.lib.period import Period
from app.modules.reports.models import REPORTS

WEEK = Period.week_of(date(2026, 9, 28))
TODAY = date(2026, 10, 5)
MADE = datetime(2026, 10, 5, 4)  # 08:00 Dubai


def test_file_names():
    assert file_name('client_servicing', WEEK) == 'OVP-Wk40-Client-Servicing.pdf'
    assert file_name('consolidated', Period.month_of(date(2026, 9, 1))) == 'OVP-2026-09-Consolidated.pdf'


@pytest.mark.parametrize('report', list(REPORTS))
def test_every_report_renders(app, db_session, report):
    with app.test_request_context():
        html = render_html(report, build(WEEK, TODAY), MADE)
    assert WEEK.label in html
    assert 'Generated Mon 5 Oct, 08:00' in html


def test_consolidated_pdf_builds(app, db_session):
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip('WeasyPrint or its system libraries are not installed')
    with app.test_request_context():
        pdf = render_pdf('consolidated', build(WEEK, TODAY), MADE)
    assert pdf.startswith(b'%PDF')
